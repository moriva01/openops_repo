import hmac
import json
import math
import os
from pathlib import Path
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
import uuid

import psycopg
from psycopg.types.json import Jsonb
from psycopg.rows import dict_row
from receiver import monitoring

LOCK = threading.Lock()
SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry_events (
  event_id uuid PRIMARY KEY,
  host_id text NOT NULL,
  hostname text NOT NULL,
  observed_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  payload jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS telemetry_host_time ON telemetry_events(host_id,observed_at DESC);
CREATE TABLE IF NOT EXISTS receiver_schema(version integer PRIMARY KEY);
INSERT INTO receiver_schema VALUES(1) ON CONFLICT DO NOTHING;
"""


def connection():
    return psycopg.connect(connect_timeout=3, options=os.environ.get("PGOPTIONS", "-c statement_timeout=4000"))


def initialize():
    with connection() as db:
        db.execute(SCHEMA)
        monitoring.initialize(db)


def log(action, **fields):
    entry = json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "action": action, **fields})
    with LOCK:
        print(entry, flush=True)
        with (Path(os.environ.get("OPENOPS_LOG_DIR", "/app/logs")) / "receiver.jsonl").open("a") as stream:
            stream.write(entry + "\n")


class EventConflict(Exception):
    pass


def validate(batch):
    if not isinstance(batch, dict) or batch.get("schema") != "openops.batch.v1":
        raise ValueError("Expected openops.batch.v1")
    events = batch.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 50:
        raise ValueError("Batch must contain 1..50 events")
    ids = set()
    for item in events:
        if not isinstance(item, dict) or item.get("schema") != "openops.telemetry.v1":
            raise ValueError("Expected openops.telemetry.v1 event")
        event_id = str(uuid.UUID(item.get("event_id", "")))
        if item["event_id"] != event_id or event_id in ids:
            raise ValueError("Event IDs must be unique canonical UUIDs within a batch")
        ids.add(event_id)
        if item.get("host_id") != os.environ["OPENOPS_HOST_ID"]:
            raise ValueError("Host is not registered for this credential")
        if not isinstance(item.get("hostname"), str) or not 1 <= len(item["hostname"]) <= 253:
            raise ValueError("Invalid hostname")
        stamp = datetime.fromisoformat(item.get("observed_at", "").replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            raise ValueError("Timestamp requires timezone")
        if (stamp - datetime.now(timezone.utc)).total_seconds() > 300:
            raise ValueError("Timestamp more than five minutes in the future")
        for key in ("host", "application", "systemd_units"):
            if not isinstance(item.get(key), dict):
                raise ValueError(key + " must be an object")
        if not isinstance(item.get("collection_errors"), list):
            raise ValueError("collection_errors must be an array")
        # Traverse numbers to reject non-finite metrics even outside known fields.
        def check(value):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Non-finite metric")
            if isinstance(value, dict):
                for v in value.values():
                    check(v)
            elif isinstance(value, list):
                for v in value:
                    check(v)
        check(item)
    return events


def persist(events):
    accepted, inserted = [], 0
    # Acknowledgement is produced only after the transaction context commits.
    with connection() as db:
        for item in events:
            row = db.execute("""INSERT INTO telemetry_events(event_id,host_id,hostname,observed_at,payload)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(event_id) DO NOTHING RETURNING event_id""",
                (item["event_id"], item["host_id"], item["hostname"], item["observed_at"], Jsonb(item))).fetchone()
            if row:
                inserted += 1
            else:
                stored = db.execute("SELECT payload FROM telemetry_events WHERE event_id=%s", (item["event_id"],)).fetchone()[0]
                if stored != item:
                    raise EventConflict("Event ID already stored with different content")
            accepted.append(item["event_id"])
    return {"accepted_event_ids": accepted, "inserted": inserted, "duplicates": len(accepted) - inserted}


class Handler(BaseHTTPRequestHandler):
    server_version = "OpenOpsReceiver/0.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_):
        pass

    def reply(self, code, body):
        raw = json.dumps(body, default=str, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self, env):
        token = os.environ[env]
        return hmac.compare_digest(self.headers.get("Authorization", "").encode(), ("Bearer " + token).encode())

    def do_POST(self):
        path = urlsplit(self.path).path
        if path in ("/api/monitors/configure", "/api/alerts/acknowledge"):
            if not self.authorized("OPENOPS_ADMIN_TOKEN"):
                self.reply(403, {"error": "Operator credential required"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192:
                    raise ValueError("Invalid body size")
                body = json.loads(self.rfile.read(size))
                with connection() as db:
                    db.row_factory = dict_row
                    if path.endswith("configure"):
                        monitoring.configure(db, body)
                    else:
                        monitoring.acknowledge(db, int(body["id"]))
                self.reply(200, {"status": "updated"})
            except (ValueError,TypeError,KeyError,OverflowError):
                self.reply(400, {"error": "Invalid change; active alert conditions cannot be redefined"})
            except psycopg.Error:
                self.reply(503, {"error": "Storage unavailable"})
            return
        if not self.authorized("OPENOPS_INGEST_TOKEN"):
            self.close_connection = True
            self.reply(401, {"error": "Ingestion credential required"})
            return
        if urlsplit(self.path).path != "/api/ingest":
            self.close_connection = True
            self.reply(404, {"error": "Not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2 * 1024 * 1024:
                self.close_connection = True
                self.reply(413, {"error": "Batch size must be 1 byte..2 MiB"})
                return
            events = validate(json.loads(self.rfile.read(size)))
            result = persist(events)
            log("batch.committed", host_id=events[0]["host_id"], inserted=result["inserted"], duplicates=result["duplicates"])
            self.reply(200, result)
        except EventConflict:
            self.reply(409, {"error": "Event ID conflicts with stored content; batch rolled back"})
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            self.reply(400, {"error": "Invalid telemetry batch"})
        except psycopg.Error as error:
            log("storage.error", error_type=type(error).__name__)
            self.reply(503, {"error": "Storage unavailable; retain batch for retry"})
        except (TimeoutError, OSError):
            self.close_connection = True

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            raw = Path("/app/receiver/index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if path in ("/health/live", "/health/ready"):
            try:
                if path.endswith("ready"):
                    with connection() as db:
                        db.execute("SELECT 1 FROM receiver_schema").fetchone()
                self.reply(200, {"status": "ok", "service": "openops-receiver"})
            except psycopg.Error:
                self.reply(503, {"status": "storage_unavailable"})
            return
        if not (self.authorized("OPENOPS_READ_TOKEN") or self.authorized("OPENOPS_ADMIN_TOKEN")):
            self.reply(401, {"error": "Read credential required"})
            return
        try:
            with connection() as db:
                if path == "/api/dashboard":
                    db.row_factory = dict_row
                    self.reply(200, monitoring.dashboard(db))
                elif path == "/api/hosts":
                    rows = db.execute("""SELECT host_id, count(*) samples, max(observed_at) latest_observed_at,
                        max(received_at) latest_received_at,
                        extract(epoch FROM clock_timestamp()-max(observed_at)) observation_age_seconds
                        FROM telemetry_events GROUP BY host_id ORDER BY host_id""").fetchall()
                    self.reply(200, {"hosts": [dict(zip(("host_id", "samples", "latest_observed_at", "latest_received_at", "observation_age_seconds"), r)) for r in rows]})
                elif path == "/api/events":
                    limit = int(parse_qs(urlsplit(self.path).query).get("limit", ["20"])[0])
                    if not 1 <= limit <= 100:
                        raise ValueError()
                    rows = db.execute("SELECT payload,received_at FROM telemetry_events ORDER BY observed_at DESC,event_id LIMIT %s", (limit,)).fetchall()
                    self.reply(200, {"events": [{"telemetry": r[0], "received_at": r[1]} for r in rows]})
                else:
                    self.reply(404, {"error": "Not found"})
        except (ValueError, TypeError):
            self.reply(400, {"error": "Invalid query"})
        except psycopg.Error:
            self.reply(503, {"error": "Storage unavailable"})


def main():
    for key in ("OPENOPS_INGEST_TOKEN", "OPENOPS_READ_TOKEN"):
        if len(os.environ.get(key, "")) < 24:
            raise SystemExit("Configure private receiver credentials before startup")
    initialize()
    log("receiver.started", schema_version=1)
    if os.environ.get("OPENOPS_MONITOR_ENABLED", "true") == "true":
        threading.Thread(target=monitoring.loop,args=(connection,log),daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("OPENOPS_PORT", "8096"))), Handler).serve_forever()


if __name__ == "__main__":
    main()
