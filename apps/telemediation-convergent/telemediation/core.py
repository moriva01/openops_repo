"""Durable ingestion, mediation and delivery, independent of proprietary formats."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from datetime import datetime

KINDS = ("voice", "sms", "data")
SERVICES = ("ingress", "mediation", "delivery")


def connect():
    path = Path(os.environ.get("TMC_DB", "var/telemediation.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def initialize(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
    INSERT OR IGNORE INTO schema_version VALUES(1);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS heartbeats(service TEXT PRIMARY KEY, seen REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS records(
      id INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
      received REAL NOT NULL, updated REAL NOT NULL, status TEXT NOT NULL,
      payload TEXT NOT NULL, normalized TEXT, output_portal TEXT, error TEXT);
    CREATE INDEX IF NOT EXISTS records_state ON records(status,id);
    CREATE INDEX IF NOT EXISTS records_kind ON records(kind,received);
    CREATE TABLE IF NOT EXISTS outputs(
      id INTEGER PRIMARY KEY, record_id INTEGER UNIQUE NOT NULL REFERENCES records(id),
      portal TEXT NOT NULL, created REAL NOT NULL, body TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS audit(
      id INTEGER PRIMARY KEY, timestamp REAL NOT NULL, action TEXT NOT NULL,
      subject TEXT NOT NULL, detail TEXT NOT NULL);
    """)
    for service in SERVICES:
        db.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (service + ".enabled", "true"))
    for kind in KINDS:
        for direction in ("input", "output"):
            db.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (direction + "." + kind, "true"))
        db.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", ("route." + kind, kind))
    db.commit()


def value(db, key):
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def enabled(db, key):
    return value(db, key) == "true"


def audit(db, action, subject, detail):
    db.execute("INSERT INTO audit(timestamp,action,subject,detail) VALUES(?,?,?,?)",
               (time.time(), action, subject, detail))


def heartbeat(db, service):
    db.execute("INSERT INTO heartbeats VALUES(?,?) ON CONFLICT(service) DO UPDATE SET seen=excluded.seen",
               (service, time.time()))
    db.commit()


def configure(db, key, setting):
    if not isinstance(key, str):
        raise ValueError("Setting key must be a string")
    if key.startswith("route.") and key[6:] in KINDS:
        if setting not in KINDS:
            raise ValueError("Unknown destination portal")
    elif key in [s + ".enabled" for s in SERVICES] + [d + "." + k for d in ("input", "output") for k in KINDS]:
        if type(setting) is not bool:
            raise ValueError("Enabled state must be a JSON boolean")
        setting = str(setting).lower()
    else:
        raise ValueError("Unknown setting")
    with db:
        db.execute("UPDATE settings SET value=? WHERE key=?", (setting, key))
        audit(db, "setting.changed", key, setting)


class Unavailable(Exception):
    pass


class Conflict(Exception):
    pass


def ingest(db, kind, payload):
    if kind not in KINDS:
        raise ValueError("Unknown input portal")
    if not enabled(db, "ingress.enabled") or not enabled(db, "input." + kind):
        raise Unavailable("Input portal is disabled")
    if not isinstance(payload, dict):
        raise ValueError("Record must be a JSON object")
    event_id = payload.get("event_id")
    if not isinstance(event_id, str) or not 1 <= len(event_id) <= 120:
        raise ValueError("event_id must contain 1 to 120 characters")
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    now = time.time()
    with db:
        # Serialize retries and conflict checks across independent API connections.
        db.execute("BEGIN IMMEDIATE")
        old = db.execute("SELECT id,kind,payload,status FROM records WHERE event_id=?", (event_id,)).fetchone()
        if old:
            if old["kind"] != kind or old["payload"] != body:
                raise Conflict("event_id already exists with different content")
            return {"record_id": old["id"], "duplicate": True, "status": old["status"]}
        cur = db.execute("INSERT INTO records(event_id,kind,received,updated,status,payload) VALUES(?,?,?,?,?,?)",
                         (event_id, kind, now, now, "received", body))
        audit(db, "record.received", event_id, kind)
        return {"record_id": cur.lastrowid, "duplicate": False, "status": "received"}


def normalized(kind, payload):
    for key in ("subscriber_id", "occurred_at"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError(key + " is required")
    stamp = datetime.fromisoformat(payload["occurred_at"].replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise ValueError("occurred_at must include a timezone")
    field, unit = {"voice": ("duration_seconds", "seconds"), "sms": ("message_count", "messages"),
                   "data": ("bytes_used", "bytes")}[kind]
    quantity = payload.get(field)
    if type(quantity) is not int or quantity < 0:
        raise ValueError(field + " must be a non-negative integer")
    return {
        "schema": "tmc.usage.v1", "event_id": payload["event_id"], "service_type": kind,
        "subscriber_ref": hashlib.sha256(payload["subscriber_id"].encode()).hexdigest(),
        "occurred_at": stamp.isoformat(), "quantity": quantity, "unit": unit,
        "provenance": {"input_portal": kind, "synthetic_lab": True},
    }


def mediate_once(db, batch=50):
    if not enabled(db, "mediation.enabled"):
        return 0
    processed = 0
    with db:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute("SELECT * FROM records WHERE status='received' ORDER BY id LIMIT ?", (batch,)).fetchall()
        for row in rows:
            try:
                body = normalized(row["kind"], json.loads(row["payload"]))
                target = value(db, "route." + row["kind"])
                db.execute("UPDATE records SET normalized=?,output_portal=?,status='mediated',updated=? WHERE id=?",
                           (json.dumps(body), target, time.time(), row["id"]))
                audit(db, "record.mediated", row["event_id"], target)
            except (ValueError, TypeError) as error:
                db.execute("UPDATE records SET status='rejected',error=?,updated=? WHERE id=?",
                           (str(error), time.time(), row["id"]))
                audit(db, "record.rejected", row["event_id"], str(error))
            processed += 1
    return processed


def deliver_once(db, batch=50):
    if not enabled(db, "delivery.enabled"):
        return 0
    count = 0
    with db:
        db.execute("BEGIN IMMEDIATE")
        for kind in KINDS:
            if not enabled(db, "output." + kind):
                continue
            rows = db.execute("SELECT * FROM records WHERE status='mediated' AND output_portal=? ORDER BY id LIMIT ?",
                              (kind, batch)).fetchall()
            for row in rows:
                db.execute("INSERT INTO outputs(record_id,portal,created,body) VALUES(?,?,?,?)",
                           (row["id"], kind, time.time(), row["normalized"]))
                db.execute("UPDATE records SET status='delivered',updated=? WHERE id=?", (time.time(), row["id"]))
                audit(db, "record.delivered", row["event_id"], kind)
                count += 1
    return count


def snapshot(db):
    now = time.time()
    beats = dict(db.execute("SELECT service,seen FROM heartbeats"))
    services = {name: {"enabled": enabled(db, name + ".enabled"),
                       "heartbeat_age_seconds": round(now - beats[name], 2) if name in beats else None,
                       "alive": name in beats and now - beats[name] < 15} for name in SERVICES}
    counts = {r[0]: r[1] for r in db.execute("SELECT status,count(*) FROM records GROUP BY status")}
    oldest = db.execute("SELECT min(received) FROM records WHERE status IN ('received','mediated')").fetchone()[0]
    throughput = db.execute("SELECT count(*) FROM outputs WHERE created>=?", (now - 60,)).fetchone()[0]
    latency = db.execute("SELECT avg(updated-received) FROM records WHERE status='delivered' AND updated>=?", (now - 60,)).fetchone()[0]
    return {"application": "TeleMediation Convergent", "version": "0.1.0", "synthetic_lab": True,
            "services": services, "settings": dict(db.execute("SELECT key,value FROM settings")),
            "records": {s: counts.get(s, 0) for s in ("received", "mediated", "delivered", "rejected")},
            "oldest_pending_age_seconds": round(now - oldest, 2) if oldest else 0,
            "delivered_last_60_seconds": throughput, "mean_delivery_latency_seconds_last_60": latency,
            "portals": [{"kind": k, "input_enabled": enabled(db, "input." + k),
                         "output_enabled": enabled(db, "output." + k), "route": value(db, "route." + k),
                         "pending_input": db.execute("SELECT count(*) FROM records WHERE kind=? AND status='received'", (k,)).fetchone()[0],
                         "pending_output": db.execute("SELECT count(*) FROM records WHERE output_portal=? AND status='mediated'", (k,)).fetchone()[0]} for k in KINDS]}
