# Connections, credentials and queries

## Credential inventory

| Credential | Private location | Consumer | Permission |
|---|---|---|---|
| `TMC_API_TOKEN` | A: `/etc/telemediation-convergent/runtime.env` | Portal and local collector | Read/control lab application |
| `COLLECTOR_INGEST_TOKEN` / `OPENOPS_INGEST_TOKEN` | A: `destination.env`; B: `.env` | Collector -> receiver | Submit telemetry for the registered host |
| `OPENOPS_READ_TOKEN` | B: `.env` | Legacy diagnostics | Hosts/events only |
| `OPENOPS_ADMIN_TOKEN` | B: `.env` | Connector encryption | Internal encryption secret; no interactive access |
| User password/session | Private initial note / HttpOnly cookie | Browser | Current user role |
| User-owned API token | Shown once in Admin; digest in database | API clients | Owner role, expiring/revocable |
| Host ingestion token | Shown once in Admin; digest in database | Additional collector | One registered host |
| `OPENOPS_DB_PASSWORD` | B: `.env` | OpenOps containers | Application database; never send to A |
| `OPENOPS_ZETARIS_DB_PASSWORD` | B: `.env` and provider datasource registration | Zetaris -> PostgreSQL | SELECT on `monitor_samples` |
| Zetaris login | B: `.local/zetaris.env` | UI-proxy adapter | SQL through configured account |
| Image registry login | Private Docker credential storage | Docker pull | Download Zetaris images |
| Nightshift Runtime token | Private Console/runtime state | Bounded investigation worker | Access local runtime |
| NVIDIA key | Nightshift Providers | Nightshift -> NVIDIA | Hosted models under provider terms |

No real credentials belong in the repository. They are not interchangeable. A never needs model keys, the PostgreSQL password or Zetaris login.

Read the TeleMediation token locally with `sudo cat /etc/telemediation-convergent/runtime.env` and copy only its value into the browser. For OpenOps, `python scripts/prepare_portal.py` exports the private initial admin note after readiness. API credentials are issued and assigned to users in Admin. Do not include these outputs in shared logs, screenshots or issues.

## Connect A to B

After preparing B, run on Windows:

```powershell
$app = "C:\OpenOps\openops_repo\apps\openops"
scp "$app\.local\collector-destination.env" "$app\scripts\connect_collector.sh" labadmin@192.168.1.202:~/
```

On A:

```bash
sudo bash ~/connect_collector.sh ~/collector-destination.env
sudo journalctl -u tmc-collector -n 5 --no-pager
```

The script currently validates the lab destination `192.168.1.17:8096/api/ingest`. For other addresses, explicitly update that validation as well as `OPENOPS_BIND_IP` and firewall settings. It is not a generic arbitrary-destination installer.

It installs root-readable `/etc/tmc-collector/destination.env`, adds `/etc/systemd/system/tmc-collector.service.d/destination.conf`, reloads systemd and restarts only the collector. Base settings and the application token remain separate.

Expected: `destination_configured:true`, positive `sent`, and a draining queue. After draining, `sent:1` with `queued:0` is normal. Large backlogs drain in batches of 50 per cycle. On B, `python scripts/receiver_status.py` confirms stored samples.

## Collector protocol

Authenticated Bearer POST, at most 50 events/2 MiB at the receiver. Collector HTTP timeout is five seconds. A commit may succeed even if its acknowledgement is lost; retries retain event IDs and are deduplicated.

```json
{"schema":"openops.batch.v1","events":[{"schema":"openops.telemetry.v1","event_id":"UUID","host_id":"tmc-lab-01","hostname":"telemediation-01","observed_at":"UTC timestamp","host":{},"application":{},"systemd_units":{},"collection_errors":[]}]}
```

Response after commit: `{"accepted_event_ids":["UUID"],"inserted":1,"duplicates":0}`. Replace illustrative timestamps/UUIDs with valid values. Host identity is credential-bound; timestamps more than five minutes in the future are rejected. Compare machine clocks when diagnosing 400 responses.

## Zetaris connection

Datasource `openops_pg`; internal URL `jdbc:postgresql://openops-db-1:5432/openops`; driver `org.postgresql.Driver`; restricted user `openops_zetaris`. The Zetaris driver shares the Docker network; the database has no published port.

The view exposes event/host IDs, observation epoch, CPU/memory/disk, application reachability, pending age, throughput, rejection total and VOICE output pending/enabled. The investigation view also exposes API/mediation/delivery process states, SMS/data pending counts and SMS/data output enablement. Refresh the registered datasource after updating the view.

Evaluation query:

```sql
SELECT * FROM openops_pg.monitor_samples ORDER BY observed_epoch DESC LIMIT 1
```

The adapter calls `/api/auth/login` and `/api/proxy/sql-editor/sqls/run-query` through the Zetaris UI with organization ID and request UUID. It maps returned headers/rows; numbers can arrive as strings or scientific notation. This is not direct REST `8888/api/v1.0` or client JDBC `10000`.

This prototype uses the existing lab administrator login. Production needs reduced permissions and stronger credential management. The script does not create provider API tokens.

## Diagnostics without printing keys

```powershell
docker compose exec -T db psql -U openops -d openops -c "SELECT host_id,count(*),max(observed_at) FROM telemetry_events GROUP BY host_id;"
docker compose exec -T db psql -U openops -d openops -c "SELECT name,state,source_status,last_value FROM monitors;"
docker compose exec -T db psql -U openops -d openops -c "SELECT id,state,opened_at,acknowledged_at,resolved_at FROM alerts ORDER BY id DESC LIMIT 10;"
docker compose exec -T receiver python -c "from receiver.zetaris import latest; r=latest(); print({k:r.get(k) for k in ('host_id','event_id','voice_pending')} if r else 'No samples')"
```
