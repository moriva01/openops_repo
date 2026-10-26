"""Zetaris UI-proxy adapter. No silent direct-database fallback."""
import json
import os
import threading
import time
import urllib.request
import uuid

class Zetaris:
    def __init__(self):
        self.lock = threading.Lock()
        self.token = None
        self.org = None
        self.login_at = 0

    def request(self, path, body, headers=None):
        req = urllib.request.Request(os.environ["ZETARIS_BASE_URL"].rstrip("/") + path,
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **(headers or {})})
        with urllib.request.urlopen(req, timeout=25) as response:
            return json.load(response)

    def query(self, statement, limit=100):
        with self.lock:
            if not self.token or time.monotonic() - self.login_at > 600:
                reply = self.request("/api/auth/login", {"username": os.environ["ZETARIS_USERNAME"], "password": os.environ["ZETARIS_PASSWORD"]})
                # Login shape is verified against the running UI before startup.
                self.token = reply.get("idToken") or reply.get("token") or reply.get("accessToken")
                self.org = reply.get("orgId")
                if not self.token or self.org is None:
                    raise ValueError("Unexpected Zetaris login response")
                self.login_at = time.monotonic()
            return self.request("/api/proxy/sql-editor/sqls/run-query", {"sql": statement, "limit": limit},
                                {"Authorization": "Bearer " + self.token, "X-Org-ID": str(self.org), "X-Request-ID": str(uuid.uuid4())})

ADAPTER = Zetaris()


def latest():
    reply = ADAPTER.query("SELECT * FROM openops_pg.monitor_samples ORDER BY observed_epoch DESC LIMIT 1", 1)
    rows = reply.get("records", reply.get("data")) if isinstance(reply, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Unexpected Zetaris result shape")
    if not rows:
        return None
    if isinstance(rows[0], dict):
        return rows[0]
    headers = reply.get("headers")
    if not isinstance(headers, list) or len(headers) != len(rows[0]):
        raise ValueError("Missing Zetaris column headers")
    return dict(zip(headers, rows[0]))
