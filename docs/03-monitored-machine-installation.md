# Install machine A: TeleMediation and collector

## Check Linux prerequisites

```bash
cat /etc/os-release
python3 --version
command -v systemctl
python3 -c 'import sqlite3; print(sqlite3.connect(":memory:").execute("SELECT json_extract(?,?)", ("{\"ok\":1}","$.ok")).fetchone())'
```

Python >=3.9 and SQLite JSON functions are required. Install a compatible interpreter through your distribution if missing; do not blindly replace the Python used by OS tools. Installers check prerequisites but do not install packages automatically.

## Build packages from source

From `apps/telemediation-convergent`, on Windows or Linux with Python:

```text
python scripts/build_package.py
python scripts/build_collector.py
```

Outputs: `dist/telemediation-convergent-0.1.0.tar.gz`, `dist/tmc-collector-0.1.0.tar.gz` and SHA-256 files. Builders exclude credentials, runtime state and vendor material.

From Windows, adjusting the checkout location:

```powershell
$repo = "C:\OpenOps\openops_repo"
scp "$repo\apps\telemediation-convergent\dist\telemediation-convergent-0.1.0.tar.gz" "$repo\apps\telemediation-convergent\dist\tmc-collector-0.1.0.tar.gz" labadmin@192.168.1.202:~/
```

## Install the application

On Linux:

```bash
mkdir -p ~/tmc-app-install
tar -xzf ~/telemediation-convergent-0.1.0.tar.gz -C ~/tmc-app-install
cd ~/tmc-app-install/telemediation-convergent
sudo bash scripts/install.sh
sudo systemctl status tmc-api tmc-mediation tmc-delivery --no-pager
curl http://127.0.0.1:8095/health/live
```

Source is installed at `/opt/telemediation-convergent`, state at `/var/lib/telemediation-convergent/state.sqlite3`, and private configuration at `/etc/telemediation-convergent/runtime.env`. Services run as `tmc`, not root. The application uses dedicated paths, database files and service names.

The installer refuses to overwrite an existing installation. This is not an upgrade procedure; do not delete existing directories to force it.

## Token and portal

Read only locally; do not paste this output into chats:

```bash
sudo cat /etc/telemediation-convergent/runtime.env
```

Use `TMC_API_TOKEN` in the portal. Default access uses an SSH tunnel; follow the firewall guide for direct IP access. Open `http://192.168.1.202:8095`, enter the token and select Connect. Send one group of records: voice/SMS/data should reach `delivered`. Delivered means published to the local outbox, not acknowledged by an external telecom operator.

## Install the collector

```bash
mkdir -p ~/tmc-collector-install
tar -xzf ~/tmc-collector-0.1.0.tar.gz -C ~/tmc-collector-install
cd ~/tmc-collector-install/telemediation-convergent
sudo bash scripts/install_collector.sh
sudo systemctl status tmc-collector --no-pager
sudo python3 scripts/check_collector.py
sudo journalctl -u tmc-collector -n 5 --no-pager
```

This adds `/etc/tmc-collector/collector.env`, `/var/lib/tmc-collector/spool.sqlite3` and `tmc-collector.service`. It does not restart the application. The installer defaults to host ID `tmc-lab-01`; if changed, it must match receiver `OPENOPS_HOST_ID`.

Initially, `destination_configured:false`, `sent:0`, and `queued` grows every 15 seconds. This proves local collection, not delivery. The first continuous CPU sample can be null because no measurement interval exists yet.

After installing B, continue with [machine-to-machine connectivity](05-connections-and-credentials.md).
