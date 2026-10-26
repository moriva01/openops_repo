"""Root-only local diagnostic; load exact key/value settings without shell evaluation."""
import os
from pathlib import Path
import sys

sys.path.insert(0, "/opt/telemediation-convergent")
for location in ("/etc/telemediation-convergent/runtime.env", "/etc/tmc-collector/collector.env"):
    for line in Path(location).read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ[key.strip()] = val.strip()
from telemediation.collector import main
sys.argv = [sys.argv[0], "--once"]
main()
