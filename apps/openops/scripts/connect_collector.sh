#!/usr/bin/env bash
# Run on the monitored VM after SCP of this script and the private destination file.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo bash connect_collector.sh collector-destination.env'; exit 1; }
SOURCE=${1:-collector-destination.env}
[[ -f "$SOURCE" && -f /etc/tmc-collector/collector.env && -f /etc/systemd/system/tmc-collector.service ]] || {
  echo 'Destination file or existing collector installation missing.'; exit 1
}
# Parse, do not source credentials as shell code. Validate expected keys without printing values.
python3 - "$SOURCE" <<'PY'
from pathlib import Path
import sys
from urllib.parse import urlsplit
settings = dict(line.split('=',1) for line in Path(sys.argv[1]).read_text().splitlines() if line and not line.startswith('#'))
assert set(settings) == {'COLLECTOR_INGEST_URL','COLLECTOR_INGEST_TOKEN'}, 'Unexpected destination keys'
target = urlsplit(settings['COLLECTOR_INGEST_URL'])
assert target.scheme in ('http','https') and target.hostname == '192.168.1.17' and target.port == 8096 and target.path == '/api/ingest', 'Unexpected receiver address'
assert len(settings['COLLECTOR_INGEST_TOKEN']) >= 24, 'Invalid ingestion credential'
PY
chmod 600 "$SOURCE"
install -m 600 "$SOURCE" /etc/tmc-collector/destination.env
install -d -m 755 /etc/systemd/system/tmc-collector.service.d
cat > /etc/systemd/system/tmc-collector.service.d/destination.conf <<'EOF'
[Service]
EnvironmentFile=/etc/tmc-collector/destination.env
EOF
systemctl daemon-reload
systemctl restart tmc-collector
echo 'Collector destination configured. After 20 seconds, inspect journalctl -u tmc-collector -n 5 --no-pager.'
