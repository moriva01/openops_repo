#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo bash scripts/install.sh'; exit 1; }
command -v python3 >/dev/null || { echo 'Python 3.9+ is required'; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3,9), "Python 3.9+ is required"'
python3 -c 'import sqlite3; db=sqlite3.connect(":memory:"); db.execute("SELECT json_extract(?, ?)", ("{\"ok\":1}", "$.ok")).fetchone()' || {
  echo 'SQLite JSON functions are required; no installation changes were made.'; exit 1
}
command -v systemctl >/dev/null || { echo 'systemd is required'; exit 1; }
BASE=/opt/telemediation-convergent
STATE=/var/lib/telemediation-convergent
CONFIG=/etc/telemediation-convergent
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ -e "$BASE" || -e "$STATE" || -e "$CONFIG" ]]; then
  echo 'Existing installation detected; refusing to overwrite. Back up and use a reviewed upgrade.'; exit 1
fi
for ROLE in api mediation delivery; do
  if [[ -e "/etc/systemd/system/tmc-${ROLE}.service" ]]; then
    echo "Existing tmc-${ROLE} unit detected; refusing to overwrite."; exit 1
  fi
done
getent passwd tmc >/dev/null || useradd --system --home-dir "$STATE" --shell /usr/sbin/nologin tmc
install -d -m 755 "$BASE" "$CONFIG"
install -d -o tmc -g tmc -m 750 "$STATE"
cp -R "$HERE/telemediation" "$HERE/web" "$BASE/"
install -m 644 "$HERE/run.py" "$BASE/run.py"
umask 077
python3 - "$CONFIG/runtime.env" <<'PY'
import secrets, sys
from pathlib import Path
Path(sys.argv[1]).write_text('TMC_API_TOKEN='+secrets.token_urlsafe(32)+'\nTMC_DB=/var/lib/telemediation-convergent/state.sqlite3\nTMC_BIND=127.0.0.1\nTMC_PORT=8095\n')
PY
for ROLE in api mediation delivery; do
  cat > "/etc/systemd/system/tmc-${ROLE}.service" <<EOF
[Unit]
Description=TeleMediation Convergent ${ROLE}
After=network.target

[Service]
Type=simple
User=tmc
Group=tmc
WorkingDirectory=$BASE
EnvironmentFile=$CONFIG/runtime.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/env python3 $BASE/run.py $ROLE
Restart=on-failure
RestartSec=3
UMask=0027
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$STATE

[Install]
WantedBy=multi-user.target
EOF
done
systemctl daemon-reload
systemctl enable --now tmc-api tmc-mediation tmc-delivery
echo 'Installed. API binds to localhost:8095. Use an SSH tunnel for remote access.'
echo 'Private settings: /etc/telemediation-convergent/runtime.env (root only). Never paste tokens into chat.'
