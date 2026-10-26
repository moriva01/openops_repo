# Monitoring validation — 26 October 2026

## Automated

Eight tests passed against real PostgreSQL, with test data isolated in temporary schemas. Coverage: ingestion/authenticated readback, exact retries, conflicting-ID batch rollback, malformed/incorrect-host data, sustained violations, acknowledgement, distinct-sample recovery, stale/query-failure behavior, gap reset and disabled-monitor preservation.

Browser smoke checks passed in isolated headless Chrome: operator login, live dashboard, acknowledgement action, no JavaScript errors, and no horizontal page overflow at a 600px viewport. Desktop and mobile screenshots reviewed locally. Access tokens were not included in screenshots.

## Real two-node incident

- Monitored Linux VM: 192.168.1.202, host ID `tmc-lab-01`.
- Receiver/portal: Windows 192.168.1.17:8096, independent PostgreSQL application database.
- Zetaris: `openops_pg.monitor_samples`, read-only source account. Latest VM samples retrieved successfully via Zetaris UI-proxy SQL.
- User disabled TeleMediation VOICE output and generated usage records. Monitor observed two pending voice records, sustained for the configured 60-second opening duration.
- Alert 1 opened at 2026-10-26 17:13:40 UTC (12:13:40 America/Bogota).
- Portal acknowledgement succeeded at 17:14:32 UTC; alert remained active.
- User re-enabled VOICE. After two distinct healthy observations, alert resolved at 17:14:55 UTC (12:14:55 America/Bogota).
- Final monitor: normal, source status ok, voice pending 0.
- Opening source event: `399cfe57-921a-452e-bd7c-adb991bc4e66`.
- Recovery source event: `1fb9c796-9bff-4ed5-b93c-bf8270b5be8a`.
- History retained opened -> acknowledged -> resolved. No synthetic test event was injected into the production telemetry stream.

## Limits

