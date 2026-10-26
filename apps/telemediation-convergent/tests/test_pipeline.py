import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import urllib.error
import socket

from telemediation.core import (Conflict, Unavailable, configure, connect, deliver_once,
                               heartbeat, ingest, initialize, mediate_once, snapshot)

ROOT = Path(__file__).resolve().parents[1]


def record(event_id="event-1", **extra):
    return {"event_id": event_id, "subscriber_id": "synthetic-001", "occurred_at": "2026-10-26T12:00:00Z",
            "duration_seconds": 30, **extra}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("TMC_DB")
        os.environ["TMC_DB"] = str(Path(self.temp.name) / "test.sqlite3")
        self.db = connect()
        initialize(self.db)

    def tearDown(self):
        self.db.close()
        if self.old is None:
            os.environ.pop("TMC_DB", None)
        else:
            os.environ["TMC_DB"] = self.old
        self.temp.cleanup()

    def test_three_channels_and_common_subscriber(self):
        for kind, field, amount in [("voice", "duration_seconds", 30), ("sms", "message_count", 2), ("data", "bytes_used", 4096)]:
            ingest(self.db, kind, record(kind, **{field: amount}))
        self.assertEqual(mediate_once(self.db), 3)
        self.assertEqual(deliver_once(self.db), 3)
        outputs = [json.loads(r[0]) for r in self.db.execute("SELECT body FROM outputs")]
        self.assertEqual(len({r["subscriber_ref"] for r in outputs}), 1)
        self.assertEqual({r["unit"] for r in outputs}, {"seconds", "messages", "bytes"})
        self.assertNotIn("subscriber_id", outputs[0])

    def test_retry_deduplicates_and_conflicting_content_rejected(self):
        ingest(self.db, "voice", record())
        self.assertTrue(ingest(self.db, "voice", record())["duplicate"])
        with self.assertRaises(Conflict):
            ingest(self.db, "voice", record(duration_seconds=99))
        mediate_once(self.db)
        deliver_once(self.db)
        mediate_once(self.db)
        deliver_once(self.db)
        self.assertEqual(self.db.execute("SELECT count(*) FROM outputs").fetchone()[0], 1)

    def test_output_outage_then_durable_recovery(self):
        configure(self.db, "output.voice", False)
        ingest(self.db, "voice", record())
        mediate_once(self.db)
        self.assertEqual(deliver_once(self.db), 0)
        self.db.close()
        self.db = connect()
        self.assertEqual(snapshot(self.db)["records"]["mediated"], 1)
        configure(self.db, "output.voice", True)
        self.assertEqual(deliver_once(self.db), 1)

    def test_mediation_pause_keeps_queue(self):
        configure(self.db, "mediation.enabled", False)
        ingest(self.db, "voice", record())
        self.assertEqual(mediate_once(self.db), 0)
        self.assertEqual(snapshot(self.db)["records"]["received"], 1)

    def test_validation_rejects_bad_quantity_and_timezone(self):
        ingest(self.db, "voice", record("bad-number", duration_seconds=-1))
        ingest(self.db, "voice", record("bad-date", occurred_at="2026-10-26T12:00:00"))
        mediate_once(self.db)
        self.assertEqual(snapshot(self.db)["records"]["rejected"], 2)
        self.assertEqual(deliver_once(self.db), 0)

    def test_disabled_input_returns_unavailable(self):
        configure(self.db, "input.voice", False)
        with self.assertRaises(Unavailable):
            ingest(self.db, "voice", record())

    def test_heartbeat_distinct_from_logical_pause(self):
        heartbeat(self.db, "mediation")
        configure(self.db, "mediation.enabled", False)
        state = snapshot(self.db)["services"]["mediation"]
        self.assertTrue(state["alive"])
        self.assertFalse(state["enabled"])


class HttpTests(unittest.TestCase):
    def test_packaged_entrypoint_auth_and_end_to_end(self):
        with tempfile.TemporaryDirectory() as temp:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            token = "test-only-token-not-a-real-credential"
            env = {**os.environ, "TMC_DB": str(Path(temp) / "http.sqlite3"), "TMC_PORT": str(port), "TMC_API_TOKEN": token}
            process = subprocess.Popen([sys.executable, str(ROOT / "run.py"), "all"], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            base = "http://127.0.0.1:" + str(port)
            def request(path, body=None, authorized=True):
                headers = {"Authorization": "Bearer " + token} if authorized else {}
                if body is not None:
                    headers["Content-Type"] = "application/json"
                req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
                with urllib.request.urlopen(req, timeout=3) as response:
                    return json.load(response)
            try:
                for _ in range(60):
                    try:
                        request("/health/live", authorized=False)
                        break
                    except OSError:
                        if process.poll() is not None:
                            self.fail(process.stderr.read().decode())
                        time.sleep(.1)
                else:
                    self.fail("API did not start")
                with self.assertRaises(urllib.error.HTTPError) as error:
                    request("/api/status", authorized=False)
                self.assertEqual(error.exception.code, 401)
                request("/api/inputs/voice", record())
                for _ in range(60):
                    output = request("/api/outputs/voice")
                    if output["records"]:
                        break
                    time.sleep(.1)
                self.assertEqual(output["records"][0]["usage"]["quantity"], 30)
                self.assertEqual(request("/api/convergence")["usage"][0]["unit"], "seconds")
                self.assertEqual(request("/api/outputs/voice?after=" + str(output["next_cursor"]))["records"], [])
                self.assertTrue(request("/health/ready")["services"]["delivery"]["alive"])
            finally:
                process.terminate()
                process.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main()
