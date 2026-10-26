# Monitoring validation — 26 October 2026

## Automated

Twenty-two tests passed against real PostgreSQL, with test data isolated in temporary schemas. Coverage: ingestion/authenticated readback, exact retries, conflicting-ID batch rollback, malformed/incorrect-host data, sustained violations, acknowledgement, distinct-sample recovery, stale/query-failure behavior, gap reset and disabled-monitor preservation.

Browser smoke checks passed in isolated headless Chrome: operator login, live dashboard, acknowledgement action, no JavaScript errors, and no horizontal page overflow at a 600px viewport. Desktop and mobile screenshots reviewed locally. Access tokens were not included in screenshots.

## Real two-node incident

- Monitored Linux VM: 192.168.1.202. Runtime host identity is omitted from this public validation record; `tmc-lab-01` is the neutral deployment example.
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

This validates one monitor and one real incident, not production reliability or a complete operations platform. Dashboard charts read PostgreSQL directly; monitor evaluation retrieves through Zetaris. Incident correlation and broader live/provider evaluation remain future work. Console roles, multiple-host registration, monitor management and opt-in notification connectors are now implemented. No AI claim is made for the deterministic alert evaluator.

## Real AI investigation

Run `inv_4878c739484741e0828722bb892fc3a0` analyzed the retained Alert 1 incident through Zetaris timeline and portal-service tools. It identified disabled VOICE output with active processes and cited four source observations. The evaluator returned `supported` with no issues; this remains a supported hypothesis, not proof of causation. No remediation occurred.

Nightshift routed three calls to NVIDIA `nvidia/nemotron-3.5-bolt-e4b`: planner receipt `rcpt_req_vlir22sz`, investigator `rcpt_req_et407tlj`, evaluator `rcpt_req_ux33k6ns`. Recorded generation durations were 2944, 10495 and 1381 milliseconds. Earlier timeout, malformed-report and provider failures remain in traces; no successful analysis is claimed for those attempts. A previous report was preserved when creating this analysis.

Fourteen investigation tests cover citation contracts, abstention, context isolation, idempotent ingestion, transaction rollback, tool execution, bounded revision, queue deduplication, preserved reports, retry limits and provider failure without fabricated results. These supplement eight receiver/monitor tests.

AI portal smoke checks also passed at 1440px and 600px: completed report, supported evaluator verdict, zero JavaScript errors and no horizontal overflow. The mobile screenshot was visually reviewed.

## Console expansion — 26 October 2026

33 tests passed. Coverage includes prior ingestion/monitor/AI behavior plus password hashing and sessions, revoked/expired/reassigned tokens, last-admin protection, API role enforcement, host-scoped ingestion and conditions, above/below severity escalation/de-escalation, ticket linking and acknowledgement removal, encrypted secrets, disabled connector behavior, idempotent outbox and actual local HTTP webhook delivery. Test accounts and telemetry use isolated temporary schemas.

Production retained its original telemetry, Alert 1 and both completed investigation reports. Only username admin exists. A private database dump preceded migration. Live ingestion and Zetaris evaluation remained healthy.

Headless Chrome checked all five independent sections, existing per-alert investigation, all six admin forms, and 1440px/600px/390px layouts without JavaScript errors or page overflow. Screenshots were reviewed locally. No external notification destination was configured. Real email/SMS provider delivery is not claimed.
