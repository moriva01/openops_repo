# User guide

## TeleMediation Convergent

Open the :8095 portal and enter the application token. Processing controls pause application logic rather than terminating processes; heartbeats can remain healthy. Input/Output controls enable individual portals.

Send voice, SMS and data records creates one synthetic record per channel. The lifecycle is received -> mediated -> delivered. Invalid usage is rejected with a reason. Identical event-ID/content retries are idempotent; changed content with the same ID conflicts.

Output portals are cursor APIs, not telecom protocol sockets. `GET /api/outputs/voice?after=0` and SMS/data equivalents return up to 100 records with `next_cursor`. Consumers persist their cursor. No external billing-system acknowledgement is recorded.

`GET /api/convergence` groups by subscriber reference and service/unit. A subscriber SHA-256 is a stable pseudonym, not anonymization. Do not use real subscriber records in this lab.

## OpenOps

Open :8096, enter a read or operator token and select Connect. Tokens remain only in browser memory for the current session. The ingestion token cannot access the portal.

### Overview

Latest observed host, active alerts, VOICE backlog, CPU and CPU/memory/backlog charts. Up to 120 observations are ordered by measurement time. An old sample arriving now does not establish current health. The Zetaris badge reports the latest query status, not an AI diagnosis.

### Monitor configuration

The first monitor supports a name, a metric from a fixed list, a greater-than threshold, duration in seconds, healthy-sample recovery count and enablement. Available metrics: VOICE pending, CPU, memory and disk. Save monitor requires the operator token.

Evaluation runs every 15 seconds; slow queries can extend the effective period. Opening requires continuous observations. Repeated reads of one event do not count as new samples. Recovery requires distinct healthy samples. The same alert lifecycle is maintained instead of creating a new alert every cycle.

An open alert prevents changing its condition/threshold/duration/recovery, preserving the meaning of its evidence. Disabling the monitor preserves the alert. Re-enabling resumes evaluation with new samples.

### Alerts and Activity

View evidence exposes source, event, host, observation time, value, threshold and configuration revision. Acknowledge marks operator attention without closing the alert or changing the application. Resolved alerts retain their rows and recovery evidence. Activity records opened, acknowledged, resolved, configuration changes and no-data transitions.

No-data does not establish health: Zetaris failures, an unreachable app, missing metrics or stale telemetry do not resolve an open alert. No-data is currently a monitor/history state, not a separate availability alert.

## Guided demonstration

1. Confirm application services and VOICE output are enabled.
2. In OpenOps, keep pending > 0 for 60 seconds, recovery 2.
3. In TeleMediation, disable Output VOICE and generate records.
4. SMS/data continue; voice remains mediated. The collector submits state and backlog.
5. OpenOps moves pending -> firing and creates an alert. Acknowledge it and inspect evidence.
6. Re-enable Output VOICE. Wait for the queue to drain and two healthy samples, approximately 30 seconds plus query latency.
7. Confirm resolved history and normal monitor state.

This demonstration requires no service termination or firewall changes. Re-enable the portal afterward to restore baseline behavior.

## Not available yet

The portal does not investigate with an LLM, infer root cause, send email/webhooks/SMS, restart applications, provide full inventory management or create multiple monitors through its UI. These are planned features, not current capabilities.

## Investigate an incident

Select **Investigate** beside an alert. The background worker retrieves incident-window evidence through Zetaris and requests bounded planning, investigation and evaluation through Nightshift. Select the run under **AI investigations** to read hypotheses, alternatives, missing evidence, citations, receipts and execution trace. Resolved alerts produce historical analyses.

**New analysis** retains earlier reports. At most three runs per alert and three attempts per run are allowed. Failed requests require explicit retry. A report never performs a repair; operator review remains necessary. See [integration details](10-ai-investigation.md).
