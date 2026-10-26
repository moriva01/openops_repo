"""Read monitoring receiver state locally without displaying credentials."""
import json
from pathlib import Path
import urllib.request

root = Path(__file__).resolve().parents[1]
settings = dict(line.split("=", 1) for line in (root / ".env").read_text().splitlines() if line and not line.startswith("#"))
base = "http://" + settings.get("OPENOPS_BIND_IP", "192.168.1.17") + ":8096"
req = urllib.request.Request(base + "/api/hosts", headers={"Authorization": "Bearer " + settings["OPENOPS_READ_TOKEN"]})
with urllib.request.urlopen(req, timeout=5) as response:
    print(json.dumps(json.load(response), indent=2))
