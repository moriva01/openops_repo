# OpenOps Evidence — monitoring receiver

Current implementation: authenticated telemetry receiver, independent PostgreSQL storage, a registered read-only Zetaris datasource, deterministic monitoring and an English operations portal. Meterless Nightshift investigation uses persistent World Model evidence, bounded tools and evaluator review. Opt-in webhook, generic SMS gateway and SMTP connectors use a durable delivery outbox. TeleMediation and the collector are separate original applications under `../telemediation-convergent`.

## Start on the monitoring node

```sh
python scripts/prepare_receiver.py --platform-env "C:\OpenOps\zetaris-platform\.env"
docker compose up -d --build
docker compose ps
```

Docker runs a separate `openops` PostgreSQL instance and persistent `openops-data` volume. It never reuses Zetaris's metastore or credentials. No database port is published. Receiver binds to Windows `192.168.1.17:8096` by default. Adjust `OPENOPS_BIND_IP` in the local `.env` for another lab.

For monitoring, `prepare_receiver.py` also preserves a private Zetaris UI-login environment file in `.local/zetaris.env` using this lab's existing platform administrator settings. It does not generate or retrieve API keys. This prototype uses authenticated UI-proxy SQL; replace administrator login with appropriately scoped access before a production deployment.

Attach `zetaris-driver-1` to `openops_default` so it can reach the private application database. `scripts/start_monitoring.ps1` checks and restores that attachment when starting the stack. Ordinary container restart retains the attachment; recreating the Zetaris driver without the script requires attaching it again.

Provision the view and datasource once with `docker compose exec -T receiver python -m receiver.setup_data`. It creates `monitor_samples` in the application database and `openops_zetaris`, a login permitted to select only that view. It registers `openops_pg` and imports the view into Zetaris. These names are reserved for this lab. The PostgreSQL password is never printed. The setup script checks existing source/table names before registration; it is not a general migration system.

Generated `.env` and `.local/` contain credentials and are gitignored and excluded from Docker builds. Never paste or commit them. The receiver has separate ingestion and read credentials. Do not rotate the database password by editing `.env` alone on an existing volume.

## Portal and monitor lifecycle

For planned restarts, start with the [Windows restart order and persistence checks](../../docs/08-operations-and-migration.md#windows-restart-order). Wait for Zetaris readiness before restarting the receiver; avoid rerunning Zetaris one-shot setup jobs during ordinary restarts.

Open http://192.168.1.17:8096. Run `python scripts/prepare_portal.py` after receiver readiness to export the private `.local/admin-access.txt` note. Sign in with the generated admin password. Only admin exists initially; create other users through Admin.

Overview, Monitors, Alerts, Activity and Admin are separate pages. Host selection supports multiple collectors. Admin manages users, user-owned tokens, hosts, clients, ticket servers and opt-in connectors. Roles are enforced by API: admin controls everything; manager operates monitors and alerts without Admin; operator uses Overview, Alerts and Activity.

See [console and administration](../../docs/11-console-and-administration.md) for the current interface, roles, severity thresholds, ticket workflow and connector contracts. Conditions require sustained distinct observations; stale data cannot resolve an alert. Severity moves through configured thresholds and clear follows verified recovery.

## Collector connection

For an authenticated local webhook destination and a real opening/recovery demonstration, follow [the webhook circuit guide](../../docs/12-webhook-circuit-demo.md). It is optional and runs separately from the monitoring receiver.

Configure other applications and Microsoft Teams directly in **Admin → External connectors**. Named fields, encrypted endpoint storage and a **Test** action are available. See [outgoing webhooks and Teams](../../docs/13-outgoing-webhooks-and-teams.md).

The generated `.local/collector-destination.env` contains only the receiver endpoint and a separate ingestion token. Transfer it privately to the monitored VM using SCP; do not paste it into chat. Install it root-readable on the VM as `/etc/tmc-collector/destination.env`, then add a systemd drop-in:

```ini
[Service]
EnvironmentFile=/etc/tmc-collector/destination.env
```

Save as `/etc/systemd/system/tmc-collector.service.d/destination.conf`, run `systemctl daemon-reload` and restart `tmc-collector`. The drop-in augments existing settings and does not expose the application's control token to the monitoring receiver.

The initial lab transport is HTTP over the private LAN. It sends infrastructure status and a bearer token without encryption; restrict Windows firewall access to VM `192.168.1.202`. Use HTTPS or an SSH tunnel before deployment outside a trusted lab. No firewall or router changes happen automatically.

## Contract and integrity

- `POST /api/ingest`: bearer ingestion credential; `openops.batch.v1`, 1–50 `openops.telemetry.v1` events, max 2 MiB, 10-second read timeout.
- Only `tmc-lab-01` is registered for this credential in this version. Host identity is credential-bound; no arbitrary host enrollment.
- UUID event identity, timezone-aware observation time and required objects are validated. Non-finite metrics and timestamps over five minutes in the future are rejected. Old buffered observations remain valid.
- Events are persisted in PostgreSQL JSONB with observation and receipt timestamps kept separately. No destructive retention runs automatically yet.
- A transaction commits before `accepted_event_ids` is returned. Exact retries are acknowledged without duplicate inserts. A changed payload with the same ID returns 409 and rolls back the entire batch.
- Failed or uncertain network requests remain in the collector spool. Receiver does not silently acknowledge failed storage.
- `GET /health/live`: process liveness. `GET /health/ready`: database/schema reachability.
- `GET /api/hosts`: read credential; stored counts, last observed/received times and observation age.
- `GET /api/events?limit=20`: read credential; newest stored samples, max 100.

Initial validation checks structure rather than all metric-domain constraints. This is a bounded single-host lab receiver, not a production multi-tenant gateway. Standard-library HTTP serving, no TLS termination, no request rate limiting. Credentials and event bodies are never written to receiver logs.

## Verification

```sh
docker compose exec -T receiver python -m unittest discover -s tests -v
```

Tests use a uniquely named temporary PostgreSQL schema and remove only that schema afterward. They exercise real database transactions, duplicate handling, conflict rollback, input validation, authenticated HTTP ingestion and readback. They do not claim VM-to-Windows connectivity until actual collector events arrive.

Logs: stdout and `/app/logs/receiver.jsonl`, stored in `openops-logs`. Successful ingestion reports counts and host ID. A durable row is the evidence of reception, not merely an open TCP port.
