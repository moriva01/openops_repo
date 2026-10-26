# Acceptance tests and troubleshooting

## Automated tests

From `apps/telemediation-convergent`:

```text
python -m unittest discover -s tests -v
```

12 tests cover three channels, convergence, duplicates/conflicts, rejection, queues, pauses, recovery, authenticated HTTP, CPU/memory calculations, durable spooling and partial acknowledgements. HTTP tests use a temporary local port/database, independent of the VM application.

From prepared `apps/openops` with containers running:

```powershell
docker compose exec -T receiver python -m unittest discover -s tests -v
```

33 real-PostgreSQL and local-HTTP tests cover console permissions, sessions, tokens, host scope, severity changes, tickets, connector encryption/delivery and ingestion/authentication, deduplication, conflict rollback, validation, sustained violations, acknowledgement, distinct recovery, stale/query failures, gaps and disabled monitors. Test data is isolated in temporary schemas, not injected into production telemetry.

## Two-machine acceptance

| Step | Expected evidence |
|---|---|
| Linux API | `/health/live` returns alive |
| Processes | Three `tmc-*` units active with fresh heartbeats |
| Traffic | All three record types reach delivered |
| Collection | Real host metrics, app reachable, no collection errors |
| Transmission | `destination_configured:true`, `sent>0`, queue drains |
| Persistence | `receiver_status.py` shows samples and a recent observation |
| Zetaris | `latest()` returns a real sample ID |
| Portal | CPU/memory/backlog visible and `Zetaris · ok` |
| Failure | Blocked VOICE moves pending -> alert after configured duration |
| Acknowledgement | Alert stays active with acknowledged_at |
| Recovery | Two healthy observations, resolved alert, evidence and history |

The lab incident is recorded in `apps/openops/VALIDATION.md`. New deployments must perform their own acceptance; they do not automatically inherit that result.

## Linux diagnostics

```bash
sudo systemctl status tmc-api tmc-mediation tmc-delivery tmc-collector --no-pager
sudo journalctl -u tmc-collector -n 20 --no-pager
sudo journalctl -u tmc-mediation -n 20 --no-pager
ss -lnt | grep 8095
curl http://127.0.0.1:8095/health/live
curl http://192.168.1.17:8096/health/ready
```

The last command proves connectivity, not authenticated ingestion/storage. Run `check_collector.py` with sudo from the extracted package; it does not display tokens.

## Windows diagnostics

```powershell
docker compose ps
docker compose logs --tail 30 receiver
python scripts/receiver_status.py
Invoke-RestMethod http://192.168.1.17:8096/health/ready
docker inspect zetaris-driver-1 --format '{{json .NetworkSettings.Networks}}'
```

Do not publish full `docker inspect` output: it includes environment settings. These commands filter networking/status. Avoid full `docker compose config` in reports because it can interpolate credentials.

## Common failures

| Symptom | Check |
|---|---|
| Docker client answers but server does not | Start Desktop, finish setup/WSL, reboot if required |
| Zetaris pull requires authentication | Account registry login; never paste credentials into chat |
| Provider bootstrap still running | Wait for initial dataset load; distinguish work in progress from a failed service |
| :8095 unavailable | TMC_BIND, API service, A firewall, bridged address, or SSH tunnel |
| API 401 | Correct application token and Bearer header |
| OpenOps operation 403 | Check user role and X-OpenOps-Request header; ingestion credentials cannot operate the console |
| Collector sent 0, destination false | Missing destination/drop-in; local queueing is expected |
| Collector errors, queue grows | Windows firewall, IP/routing, receiver, ingestion token, DB status |
| Ingestion 400 | Clock synchronization, host ID, JSON/schema; do not delete the spool to hide it |
| Ingestion 409 | Event ID reused with changed content; inspect producer and preserve evidence |
| Ingestion 503 | PostgreSQL unavailable; events should remain queued |
| Zetaris cannot reach DB | Driver attachment to `openops_default`, `openops-db-1` address, datasource settings |
| Zetaris login fails | Current login in `.local/zetaris.env`, not an outdated initialization password |
| Monitor no-data | Observation age <60 seconds, reachable app, Zetaris query and available metric |
| Alert not immediate | Opening duration and distinct samples; repeated reads do not advance it |
| Alert remains after disabling monitor | Designed behavior: disabled does not mean recovered |
| Nightshift catalog but no generation | Configure provider/lane and test real text; health alone is insufficient |

Reports should include status, error type and times, never `.env`, tokens, passwords or credential-bearing payloads.
