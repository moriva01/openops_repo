#!/usr/bin/env python3
"""Run an API, mediation worker or delivery worker. Python 3.9+, no dependencies."""
import argparse
import hmac
import json
import os
from pathlib import Path
import signal
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from telemediation.core import (Conflict, Unavailable, KINDS, audit, configure, connect,
                               deliver_once, heartbeat, ingest, initialize, mediate_once, snapshot)

STOP = threading.Event()
ROOT = Path(__file__).resolve().parent


def log(event, **fields):
    print(json.dumps({"timestamp": time.time(), "event": event, **fields}), flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "TeleMediation/0.1"

    def log_message(self, fmt, *args):
        # Do not log headers, request bodies, URL queries or credentials.
        log("http.request", method=self.command)

    def send(self, code, data):
        body = json.dumps(data, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        expected = os.environ["TMC_API_TOKEN"]
        supplied = self.headers.get("Authorization", "")
        return hmac.compare_digest(supplied.encode(), ("Bearer " + expected).encode())

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            body = (ROOT / "web/index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/health/live":
            self.send(200, {"status": "alive", "application": "TeleMediation Convergent"})
            return
        if not self.authorized():
            self.send(401, {"error": "Bearer token required"})
            return
        db = connect()
        try:
            if path in ("/api/status", "/health/ready"):
                state = snapshot(db)
                ready = all(s["alive"] and s["enabled"] for s in state["services"].values())
                self.send(503 if path == "/health/ready" and not ready else 200, state)
            elif path == "/api/records":
                rows = db.execute("SELECT id,event_id,kind,status,received,updated,output_portal,error FROM records ORDER BY id DESC LIMIT 100")
                self.send(200, {"records": [dict(r) for r in rows]})
            elif path == "/api/audit":
                self.send(200, {"events": [dict(r) for r in db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100")]})
            elif path == "/api/convergence":
                # Aggregate unlike units separately: seconds are never added to bytes.
                rows = db.execute("""SELECT json_extract(body,'$.subscriber_ref') subscriber_ref,
                    json_extract(body,'$.service_type') service_type,
                    json_extract(body,'$.unit') unit, count(*) records,
                    sum(json_extract(body,'$.quantity')) quantity
                    FROM outputs GROUP BY subscriber_ref,service_type,unit
                    ORDER BY subscriber_ref,service_type LIMIT 100""")
                self.send(200, {"usage": [dict(r) for r in rows], "limit": 100})
            elif path.startswith("/api/outputs/"):
                kind = path.rsplit("/", 1)[1]
                if kind not in KINDS:
                    raise ValueError("Unknown output portal")
                query = parse_qs(urlsplit(self.path).query)
                after = int(query.get("after", ["0"])[0])
                rows = db.execute("SELECT id,body FROM outputs WHERE portal=? AND id>? ORDER BY id LIMIT 100", (kind, after)).fetchall()
                self.send(200, {"portal": kind, "records": [{"cursor": r["id"], "usage": json.loads(r["body"])} for r in rows],
                                "next_cursor": rows[-1]["id"] if rows else after})
            else:
                self.send(404, {"error": "Not found"})
        except ValueError as error:
            self.send(400, {"error": str(error)})
        except sqlite3.Error:
            self.send(503, {"error": "Storage temporarily unavailable"})
        finally:
            db.close()

    def do_POST(self):
        if not self.authorized():
            self.send(401, {"error": "Bearer token required"})
            return
        db = connect()
        self.connection.settimeout(10)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                self.send(413, {"error": "Body must contain 1 to 65536 bytes"})
                return
            def bad_number(_):
                raise ValueError("Non-finite number in JSON")
            body = json.loads(self.rfile.read(length), parse_constant=bad_number)
            if not isinstance(body, dict):
                raise ValueError("Expected JSON object")
            path = urlsplit(self.path).path
            if path.startswith("/api/inputs/"):
                self.send(202, ingest(db, path.rsplit("/", 1)[1], body))
            elif path == "/api/settings":
                configure(db, body.get("key", ""), body.get("value"))
                self.send(200, {"status": "updated"})
            else:
                self.send(404, {"error": "Not found"})
        except Conflict as error:
            self.send(409, {"error": str(error)})
        except Unavailable as error:
            self.send(503, {"error": str(error)})
        except (ValueError, TypeError, KeyError) as error:
            self.send(400, {"error": str(error)})
        except sqlite3.Error:
            self.send(503, {"error": "Storage temporarily unavailable"})
        except (TimeoutError, OSError):
            log("http.connection_interrupted")
        finally:
            db.close()


def loop(service):
    db = connect()
    try:
        while not STOP.is_set():
            try:
                heartbeat(db, service)
                count = 0
                if service == "mediation":
                    count = mediate_once(db)
                elif service == "delivery":
                    count = deliver_once(db)
                if count:
                    log("worker.processed", service=service, count=count)
            except sqlite3.Error as error:
                db.rollback()
                log("worker.storage_error", service=service, error_type=type(error).__name__)
            STOP.wait(1)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("api", "mediation", "delivery", "all"))
    args = parser.parse_args()
    token = os.environ.get("TMC_API_TOKEN", "")
    if len(token) < 24:
        parser.error("Set TMC_API_TOKEN to a private token of at least 24 characters")
    with connect() as db:
        initialize(db)
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: STOP.set())
    log("service.started", role=args.role)
    if args.role in ("mediation", "delivery"):
        loop(args.role)
        return
    services = ["ingress"] + (["mediation", "delivery"] if args.role == "all" else [])
    for service in services:
        threading.Thread(target=loop, args=(service,), daemon=True).start()
    server = ThreadingHTTPServer((os.environ.get("TMC_BIND", "127.0.0.1"), int(os.environ.get("TMC_PORT", "8095"))), Handler)
    server.timeout = 1
    while not STOP.is_set():
        server.handle_request()
    server.server_close()


if __name__ == "__main__":
    main()
