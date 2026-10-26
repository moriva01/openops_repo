"""Linux telemetry agent. Reads procfs and the local app; never invokes a model."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.request
import uuid

STOP = threading.Event()


def cpu_counters(text):
    parts = text.splitlines()[0].split()
    if parts[0] != "cpu" or len(parts) < 5:
        raise ValueError("Invalid aggregate CPU counters")
    values = [int(v) for v in parts[1:9]]
    # guest/guest_nice are already included in user/nice; do not count twice.
    return sum(values), values[3] + (values[4] if len(values) > 4 else 0)


def cpu_percent(previous, current):
    total, idle = current[0] - previous[0], current[1] - previous[1]
    if total <= 0 or idle < 0 or idle > total:
        return None
    return round(100 * (total - idle) / total, 2)


def memory_metrics(text):
    values = {}
    for line in text.splitlines():
        key, rest = line.split(":", 1)
        values[key] = int(rest.split()[0]) * 1024
    total, available = values["MemTotal"], values["MemAvailable"]
    return {"total_bytes": total, "available_bytes": available,
            "used_percent": round(100 * (total - available) / total, 2)}


class Spool:
    """Bounded durable queue; stable event IDs permit receiver-side deduplication."""
    def __init__(self, path, limit=1440):
        if limit < 1:
            raise ValueError("Spool limit must be positive")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.limit = limit
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS pending(seq INTEGER PRIMARY KEY, event_id TEXT UNIQUE, body TEXT)")
        self.db.commit()

    def add(self, packet):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO pending(event_id,body) VALUES(?,?)",
                            (packet["event_id"], json.dumps(packet, allow_nan=False)))
            count = self.db.execute("SELECT count(*) FROM pending").fetchone()[0]
            dropped = max(0, count - self.limit)
            if dropped:
                self.db.execute("DELETE FROM pending WHERE seq IN (SELECT seq FROM pending ORDER BY seq LIMIT ?)", (dropped,))
        return dropped

    def batch(self, limit=50):
        return [json.loads(r[0]) for r in self.db.execute("SELECT body FROM pending ORDER BY seq LIMIT ?", (limit,))]

    def acknowledge(self, event_ids):
        with self.db:
            self.db.executemany("DELETE FROM pending WHERE event_id=?", [(i,) for i in event_ids])

    def count(self):
        return self.db.execute("SELECT count(*) FROM pending").fetchone()[0]

    def close(self):
        self.db.close()


def app_status(base, token):
    req = urllib.request.Request(base.rstrip("/") + "/api/status", headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            raw = response.read(262145)
            if len(raw) > 262144:
                raise ValueError("Oversized app response")
            state = json.loads(raw)
        # Only documented observability fields are sent. Never forward headers,
        # environment variables, tokens, raw usage records or subscriber IDs.
        required = ("services", "records", "portals", "oldest_pending_age_seconds")
        if not isinstance(state, dict) or any(k not in state for k in required):
            raise ValueError("Invalid application telemetry schema")
        return {"reachable": True, "services": state["services"], "records": state["records"],
                "portals": state["portals"], "oldest_pending_age_seconds": state["oldest_pending_age_seconds"],
                "delivered_last_60_seconds": state.get("delivered_last_60_seconds"),
                "mean_delivery_latency_seconds_last_60": state.get("mean_delivery_latency_seconds_last_60")}
    except (OSError, ValueError, TypeError, KeyError) as error:
        return {"reachable": False, "error_type": type(error).__name__}


def collect(previous_cpu, proc=Path("/proc")):
    errors = []
    host = {}
    current_cpu = previous_cpu
    try:
        current_cpu = cpu_counters((proc / "stat").read_text())
        host["cpu_used_percent"] = cpu_percent(previous_cpu, current_cpu) if previous_cpu else None
    except (OSError, ValueError):
        errors.append("cpu_unavailable")
    try:
        host["memory"] = memory_metrics((proc / "meminfo").read_text())
        host["uptime_seconds"] = float((proc / "uptime").read_text().split()[0])
        host["load_average"] = list(os.getloadavg())
    except (OSError, ValueError, KeyError, AttributeError):
        errors.append("host_metrics_partial")
    disk = shutil.disk_usage(os.environ.get("COLLECTOR_DISK_PATH", "/"))
    host["disk"] = {"path": os.environ.get("COLLECTOR_DISK_PATH", "/"), "total_bytes": disk.total,
                    "free_bytes": disk.free, "used_percent": round(100 * disk.used / disk.total, 2)}
    units = {}
    for name in ("tmc-api", "tmc-mediation", "tmc-delivery"):
        try:
            result = subprocess.run(["systemctl", "show", name + ".service", "--property=ActiveState", "--value"],
                                    capture_output=True, text=True, timeout=1, check=False)
            state = result.stdout.strip()
            units[name] = state if result.returncode == 0 and state in ("active", "inactive", "failed", "activating", "deactivating", "reloading") else "unknown"
        except (OSError, subprocess.TimeoutExpired):
            units[name] = "unknown"
    hostname = socket.gethostname()
    packet = {"schema": "openops.telemetry.v1", "event_id": str(uuid.uuid4()),
              "host_id": os.environ.get("COLLECTOR_HOST_ID", "host-" + hashlib.sha256(hostname.encode()).hexdigest()[:16]),
              "hostname": hostname, "observed_at": datetime.now(timezone.utc).isoformat(),
              "host": host, "systemd_units": units, "collection_errors": errors,
              "application": app_status(os.environ.get("TMC_LOCAL_URL", "http://127.0.0.1:8095"), os.environ.get("TMC_API_TOKEN", ""))}
    return packet, current_cpu


def transmit(spool, url, token):
    packets = spool.batch()
    if not packets:
        return 0
    req = urllib.request.Request(url, data=json.dumps({"schema": "openops.batch.v1", "events": packets}).encode(),
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    # No immediate retry: uncertain delivery keeps the same IDs for the next cycle.
    with urllib.request.urlopen(req, timeout=5) as response:
        reply = json.loads(response.read(65537))
    accepted = reply.get("accepted_event_ids")
    if not isinstance(accepted, list) or any(not isinstance(i, str) for i in accepted):
        raise ValueError("Receiver must return accepted_event_ids")
    sent = {p["event_id"] for p in packets}
    confirmed = [i for i in accepted if i in sent]
    spool.acknowledge(confirmed)
    return len(confirmed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Print one diagnostic sample, no spool or transmission")
    args = parser.parse_args()
    if not Path("/proc/stat").exists():
        parser.error("Collector requires Linux procfs")
    interval = int(os.environ.get("COLLECTOR_INTERVAL", "15"))
    if not 5 <= interval <= 300:
        parser.error("COLLECTOR_INTERVAL must be 5..300 seconds")
    previous = cpu_counters(Path("/proc/stat").read_text())
    if args.once:
        time.sleep(.2)
        print(json.dumps(collect(previous)[0], indent=2, allow_nan=False))
        return
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: STOP.set())
    spool = Spool(os.environ.get("COLLECTOR_SPOOL", "/var/lib/tmc-collector/spool.sqlite3"))
    try:
        while not STOP.is_set():
            start = time.monotonic()
            try:
                packet, previous = collect(previous)
                dropped = spool.add(packet)
                url = os.environ.get("COLLECTOR_INGEST_URL", "")
                token = os.environ.get("COLLECTOR_INGEST_TOKEN", "")
                sent = transmit(spool, url, token) if url and token else 0
                print(json.dumps({"event": "collector.cycle", "event_id": packet["event_id"],
                                  "queued": spool.count(), "sent": sent, "retention_dropped": dropped,
                                  "destination_configured": bool(url and token)}), flush=True)
            except (OSError, ValueError, sqlite3.Error) as error:
                print(json.dumps({"event": "collector.error", "error_type": type(error).__name__,
                                  "queued": spool.count()}), flush=True)
            STOP.wait(max(0, interval - (time.monotonic() - start)))
    finally:
        spool.close()


if __name__ == "__main__":
    main()
