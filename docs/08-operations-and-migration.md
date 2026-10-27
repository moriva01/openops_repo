# Operations, backups and deployment migration

## Consolidated source versus running deployment

This checkout is the consolidated source for future changes. Copying source does not move containers, databases or private settings. The lab receiver now runs from this checkout after preserving its private credentials, host binding and existing volumes. Linux services use `/opt/telemediation-convergent`.

Both OpenOps checkouts declare the same Compose project `openops`, container names and volumes. They are not independent deployments on the same port. Never generate new passwords and apply them to an existing database volume: changing `.env` does not change its stored PostgreSQL password.

## Move the existing monitoring deployment to this checkout

This procedure was applied during AI integration. Use it when moving another existing deployment.

1. Verify services, volumes and existing credentials. Back up the database, logs and private configuration.
2. Privately copy the original `.env` to `apps/openops/.env` and required `.local` settings to `apps/openops/.local`, outside Git. Preserve current secrets. Old private screenshots/browser tests are optional, not source material.
3. Compare variable names without printing values. Set `OPENOPS_HOST_ID` explicitly to the current collector identity before recreating an existing deployment; a missing variable now defaults to `tmc-lab-01`. Changing example names does not migrate a running collector. Review `.local/zetaris.env` and addresses.
4. From `apps/openops`, run `docker compose up -d --build`. The `openops` project reuses its volumes and recreates the receiver from this source. Brief interruptions should be covered by the collector spool.
5. Restore network attachment with `scripts/start_monitoring.ps1` if needed. Moving a checkout does not require regenerating the datasource or password.
6. Verify health, ingestion, Zetaris queries and monitor state. Thereafter, operate Compose from only this checkout.

Do not use `down -v` or delete databases/settings to solve a migration. The Linux application does not need reinstallation just because the Windows repository moved.

## Neutral deployment identities

New installations use `tmc-lab-01` as the collector identity and `telemediation-01` as the example hostname. Existing runtime identities and stored observations are not rewritten by a source/documentation update.

If changing an existing deployment identity, first drain the collector spool against its current receiver configuration. Stop the collector, then coordinate `COLLECTOR_HOST_ID` on Linux with `OPENOPS_HOST_ID` in the monitoring environment. Recreate the receiver with the matching value before restarting collection. A mismatched identity is rejected; do not delete queued observations to bypass it.

Changing the Linux hostname is a separate administrator action, for example `sudo hostnamectl set-hostname telemediation-01`. Review SSH, networking and other host consumers first. Historical observations retain their recorded identity; do not include private historical exports in public demonstration material.

## Backups

### Linux

For a simple consistent copy, temporarily stop the three application services and collector, back up `/var/lib/telemediation-convergent`, `/var/lib/tmc-collector`, `/etc/telemediation-convergent` and `/etc/tmc-collector` as root, then restart services. Configuration contains secrets; encrypt/restrict backups and never commit them. Alternatively, use SQLite's backup API while writers run. Copying only a live `.sqlite3` file can miss WAL data.

Preserve the `tmc-*` units and collector drop-in, or reconstruct them on a new machine. Current installers refuse overwrite and are not version migrations.

### OpenOps PostgreSQL

From `apps/openops`, save a dump in private backup storage. Use `docker compose exec -T db pg_dump -U openops -d openops` with a writer that preserves encoding/bytes; older Windows PowerShell redirection can recode SQL. For large files, dump to a container file and use `docker cp` into private storage.

A database dump does not include global role passwords. Preserve the original `.env` and deliberately recreate the read-only role when restoring elsewhere. Back up `openops-logs` for operational logs. Telemetry, monitors, alerts and transition history live in PostgreSQL.

### Zetaris and Nightshift

Follow provider procedures for their volumes and settings, especially Zetaris `.env` and encryption material. A new password cannot replace a lost encryption-keypair password. Never commit provider keys or Runtime tokens.

## Restarts and continuity

- Enabled Linux units start through systemd. Containers use restart unless-stopped; Docker Desktop must be running.
- While the receiver is down, the collector retains up to 1440 events. Retries are deduplicated after recovery.
- If the application stops but the collector runs, it reports API unreachability and systemd process states.
- If A or the collector stops, there are no new observations. The monitor reports no-data instead of inventing recovery.
- Monitor and alert state persists. Timers use observation timestamps and freshness bounds.

### Windows restart order

Keep Docker Desktop running and leave Nightshift open with its configured provider enabled. The monitored Linux machine does not need to restart.

1. In PowerShell, change to your extracted `zetaris-platform` directory and restart only its long-running services:

   ```powershell
   docker compose restart postgres driver api ui
   docker compose ps --all
   & "$env:ProgramFiles\Git\bin\bash.exe" ./verify.sh
   ```

   Wait for PostgreSQL, driver, API and UI to become healthy and for login and SQL checks to pass. Repeat verification after startup settles. Avoid an unqualified `docker compose restart` here: it also reruns the one-shot `init` and `bootstrap` jobs without waiting for dependencies to become ready.

2. If a previous full-stack restart left `bootstrap` at exit code 1 with login `HTTP 000`, first confirm that the platform login and SQL checks now pass. Then rerun only that job and verify again:

   ```powershell
   docker compose restart bootstrap
   & "$env:ProgramFiles\Git\bin\bash.exe" ./verify.sh
   ```

   Allow bootstrap to finish before repeating verification. In the reinstall test, this recovered all nine checks. Do not change passwords based only on `HTTP 000`; inspect logs if the job fails again.

3. Change to this repository's `apps/openops` directory. Restart the OpenOps database, wait for its health check to pass, and then restart the receiver:

   ```powershell
   docker compose restart db
   docker compose ps
   ```

   Once `db` is healthy:

   ```powershell
   docker compose restart receiver
   docker compose logs --tail 20 receiver
   ```

   Check for a new `monitor.evaluated` entry with `source: zetaris` and `status: ok`, plus continuing `batch.committed` entries. If only Zetaris was restarted, restarting `db` is unnecessary; restart `receiver` after Zetaris is ready.

4. Refresh the OpenOps portal and sign in again if required. Confirm that users, clients, hosts, monitors, ticket servers, connectors, alert history and investigation reports remain. Confirm that charts receive fresh observations, then test an alert opening and recovery with the configured notification connector.

During the clean-install restart test, ingestion continued but Zetaris evaluations remained in `zetaris_HTTPError` until the receiver restarted. Two subsequent evaluations returned `ok`. The exact cause was not established; this procedure is a verified manual recovery, not proof of automatic reconnection.

Ordinary restarts retain the driver's `openops_default` attachment. If the driver was recreated instead, restore that attachment using `scripts/start_monitoring.ps1` or the documented network connection procedure. Never use `docker compose down -v` for a restart: it deletes persistent volumes.

## Credential rotation

Rotation is not automated. Update both ends of a credential and restart/recreate affected consumers without displaying secrets. Editing a PostgreSQL password in `.env` alone does not rotate an existing role; first change the role deliberately in PostgreSQL. A datasource password must also be updated in Zetaris. Replace compromised keys rather than only removing their file copies.

## Future development

Broader provider validation, incident correlation and production hardening. Multiple monitors, host administration, roles and opt-in connectors now exist; see [console guide](11-console-and-administration.md). Meterless investigation and hypothesis evaluation are implemented; see [AI integration](10-ai-investigation.md). Begin changes in this checkout, preserve tests and update implementation status. Do not present planned capabilities as working features.
