#!/usr/bin/env bash
# Add a separate monitoring collector to an already installed TeleMediation lab.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo bash scripts/install_collector.sh'; exit 1; }
BASE=/opt/telemediation-convergent
CONFIG=/etc/tmc-collector
STATE=/var/lib/tmc-collector
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ -f "$BASE/run.py" && -f /etc/telemediation-convergent/runtime.env ]] || {
  echo 'Install TeleMediation first.'; exit 1
}
[[ ! -e "$CONFIG" && ! -e "$STATE" && ! -e /etc/systemd/system/tmc-collector.service ]] || {
  echo 'Existing collector detected; refusing to overwrite.'; exit 1
}
python3 -c 'import sys; assert sys.version_info >= (3,9)'
install -m 644 "$SOURCE/telemediation/collector.py" "$BASE/telemediation/collector.py"
install -d -m 700 "$CONFIG"
install -d -m 750 -o tmc -g tmc "$STATE"
umask 077
cat > "$CONFIG/collector.env" <<'EOF'
COLLECTOR_INTERVAL=15
COLLECTOR_HOST_ID=tmc-lab-01
COLLECTOR_SPOOL=/var/lib/tmc-collector/spool.sqlite3
TMC_LOCAL_URL=http://127.0.0.1:8095
# Set the URL and separate ingestion credential once the monitoring node is ready.
COLLECTOR_INGEST_URL=
COLLECTOR_INGEST_TOKEN=
EOF
cat > /etc/systemd/system/tmc-collector.service <<'EOF'
[Unit]
Description=OpenOps Linux and TeleMediation collector
After=network.target tmc-api.service

[Service]
Type=simple
User=tmc
Group=tmc
WorkingDirectory=/opt/telemediation-convergent
EnvironmentFile=/etc/telemediation-convergent/runtime.env
EnvironmentFile=/etc/tmc-collector/collector.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/env python3 -m telemediation.collector
Restart=on-failure
RestartSec=5
UMask=0027
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/tmc-collector

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now tmc-collector
echo 'Collector installed; samples queue locally until the monitoring receiver is configured.'
echo 'Logs: journalctl -u tmc-collector --no-pager -n 10'
