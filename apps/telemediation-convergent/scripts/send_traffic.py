"""Send a bounded synthetic convergent workload through the public ingestion API."""
import argparse
from datetime import datetime, timezone
import json
import os
import time
import urllib.request
import uuid

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://127.0.0.1:8095")
parser.add_argument("--batches", type=int, default=10)
parser.add_argument("--interval", type=float, default=1)
args = parser.parse_args()
if not 1 <= args.batches <= 1000 or not .1 <= args.interval <= 60:
    parser.error("Use 1..1000 batches and a 0.1..60 second interval")
token = os.environ["TMC_API_TOKEN"]
for batch in range(args.batches):
    for kind, key, quantity in [("voice", "duration_seconds", 60), ("sms", "message_count", 1), ("data", "bytes_used", 1048576)]:
        body = {"event_id": str(uuid.uuid4()), "subscriber_id": "synthetic-subscriber-001",
                "occurred_at": datetime.now(timezone.utc).isoformat(), key: quantity}
        req = urllib.request.Request(args.url.rstrip("/") + "/api/inputs/" + kind, data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as response:
            print(kind, response.status, json.load(response)["record_id"])
    time.sleep(args.interval)
