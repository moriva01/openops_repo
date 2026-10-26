import copy
from datetime import datetime, timezone
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import urllib.error
import uuid

import psycopg
from psycopg import sql
from receiver.server import initialize, persist, validate, EventConflict


def event():
    return {"schema": "openops.telemetry.v1", "event_id": str(uuid.uuid4()),
            "host_id": os.environ["OPENOPS_HOST_ID"], "hostname": "receiver-test-only",
            "observed_at": datetime.now(timezone.utc).isoformat(), "host": {"cpu_used_percent": 4.2},
            "application": {"reachable": True}, "systemd_units": {}, "collection_errors": []}


class ReceiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_receiver_" + uuid.uuid4().hex
        cls.old_options = os.environ.get("PGOPTIONS")
        with psycopg.connect() as db:
            db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema)))
        os.environ["PGOPTIONS"] = "-c search_path=" + cls.schema + " -c statement_timeout=4000"
        initialize()

    @classmethod
    def tearDownClass(cls):
        if cls.old_options is None:
            os.environ.pop("PGOPTIONS", None)
        else:
            os.environ["PGOPTIONS"] = cls.old_options
        with psycopg.connect() as db:
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema)))

    def test_duplicate_delivery_is_acknowledged_once(self):
        item = event()
        self.assertEqual(persist([item])["inserted"], 1)
        reply = persist([item])
        self.assertEqual(reply["duplicates"], 1)
        self.assertEqual(reply["accepted_event_ids"], [item["event_id"]])

    def test_conflict_rolls_back_entire_batch(self):
        existing = event()
        persist([existing])
        changed = copy.deepcopy(existing)
        changed["host"]["cpu_used_percent"] = 99
        fresh = event()
        with self.assertRaises(EventConflict):
            persist([fresh, changed])
        # If the transaction rolled back, retry inserts this event now.
        self.assertEqual(persist([fresh])["inserted"], 1)

    def test_validation_rejects_wrong_host_timezone_and_nonfinite(self):
        for mutate in (lambda e: e.update(host_id="unregistered"),
                       lambda e: e.update(observed_at="2026-10-26T10:00:00"),
                       lambda e: e["host"].update(cpu_used_percent=float("nan"))):
            item = event()
            mutate(item)
            with self.assertRaises(ValueError):
                validate({"schema": "openops.batch.v1", "events": [item]})

    def test_http_auth_commit_and_receiver_readback(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with tempfile.TemporaryDirectory() as temp:
            env = {**os.environ, "OPENOPS_PORT": str(port), "OPENOPS_LOG_DIR": temp, "OPENOPS_MONITOR_ENABLED":"false"}
            process = subprocess.Popen([sys.executable, "-m", "receiver.server"], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            base = "http://127.0.0.1:" + str(port)
            def request(path, token=None, body=None):
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = "Bearer " + token
                req = urllib.request.Request(base + path, headers=headers,
                                             data=json.dumps(body).encode() if body is not None else None)
                with urllib.request.urlopen(req, timeout=5) as response:
                    return json.load(response)
            try:
                for _ in range(60):
                    try:
                        request("/health/ready")
                        break
                    except OSError:
                        if process.poll() is not None:
                            self.fail(process.stderr.read().decode())
                        time.sleep(.1)
                else:
                    self.fail("Receiver did not start")
                item = event()
                batch = {"schema": "openops.batch.v1", "events": [item]}
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request("/api/ingest", body=batch)
                self.assertEqual(error.exception.code, 401)
                reply = request("/api/ingest", os.environ["OPENOPS_INGEST_TOKEN"], batch)
                self.assertEqual(reply["accepted_event_ids"], [item["event_id"]])
                self.assertEqual(request("/api/ingest", os.environ["OPENOPS_INGEST_TOKEN"], batch)["duplicates"], 1)
                with self.assertRaises(urllib.error.HTTPError):
                    request("/api/hosts", os.environ["OPENOPS_INGEST_TOKEN"])
                hosts = request("/api/hosts", os.environ["OPENOPS_READ_TOKEN"])["hosts"]
                self.assertTrue(hosts)
                records = request("/api/events?limit=100", os.environ["OPENOPS_READ_TOKEN"])["events"]
                self.assertIn(item["event_id"], [r["telemetry"]["event_id"] for r in records])
            finally:
                process.terminate()
                process.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main()
