# Operations, backups and deployment migration

## Consolidated source versus running deployment

This checkout is the consolidated source for future changes. Copying source does not move containers, databases or private settings. The existing lab runs images built from the earlier `openops-evidence` directory; Linux services use `/opt/telemediation-convergent`.

Both OpenOps checkouts declare the same Compose project `openops`, container names and volumes. They are not independent deployments on the same port. Never generate new passwords and apply them to an existing database volume: changing `.env` does not change its stored PostgreSQL password.

## Move the existing monitoring deployment to this checkout

This is a maintenance-window procedure, not an action performed automatically by repository consolidation.

1. Verify services, volumes and existing credentials. Back up the database, logs and private configuration.
2. Privately copy the original `.env` to `apps/openops/.env` and required `.local` settings to `apps/openops/.local`, outside Git. Preserve current secrets. Old private screenshots/browser tests are optional, not source material.
3. Compare variable names without printing values. Older files may omit `OPENOPS_HOST_ID`; Compose defaults to `tmc-lab-01`. Review `.local/zetaris.env` and addresses.
4. From `apps/openops`, run `docker compose up -d --build`. The `openops` project reuses its volumes and recreates the receiver from this source. Brief interruptions should be covered by the collector spool.
5. Restore network attachment with `scripts/start_monitoring.ps1` if needed. Moving a checkout does not require regenerating the datasource or password.
6. Verify health, ingestion, Zetaris queries and monitor state. Thereafter, operate Compose from only this checkout.

Do not use `down -v` or delete databases/settings to solve a migration. The Linux application does not need reinstallation just because the Windows repository moved.

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

## Credential rotation

Rotation is not automated. Update both ends of a credential and restart/recreate affected consumers without displaying secrets. Editing a PostgreSQL password in `.env` alone does not rotate an existing role; first change the role deliberately in PostgreSQL. A datasource password must also be updated in Zetaris. Replace compromised keys rather than only removing their file copies.

## Future development

Meterless/World Model investigation, hypothesis evaluation, notifications and additional monitors. Begin changes in this checkout, preserve tests and update implementation status. Do not present planned capabilities as working features.
