# OpenOps Evidence — build plan

## Product

An original operations platform for small IT teams and managed service providers. It collects host/application telemetry, evaluates monitors, manages alert lifecycles and verifies recovery. The commercial hypothesis is reduced incident investigation time and must be validated with operators.

## Implemented foundation

- TeleMediation Convergent: synthetic voice, messaging and data usage, normalization, routing and output portals.
- Independent Linux collector with real host metrics and a bounded durable spool.
- Authenticated ingestion into application PostgreSQL.
- Read-only PostgreSQL view registered in Zetaris.
- Deterministic monitoring through Zetaris with evidence-bearing alert transitions.
- English portal for charts, monitor configuration, acknowledgement and history.
- A real two-machine blocked-output/recovery test; see VALIDATION.md.

## Deployment

Machine A runs the application and collector as unprivileged systemd services. Machine B runs Docker Desktop, the monitoring stack and Zetaris. Nightshift is installed separately as the active AI runtime. Model execution can use hosted NVIDIA endpoints without a local GPU.

Machine names and IDs are neutral deployment examples: telemediation-01 / tmc-lab-01. Use isolated lab data and documented interfaces.

## Remaining implementation stages

World Model persistence, Nightshift generation, bounded investigation, citation validation and critique are implemented. A real historical incident was analyzed with NVIDIA receipts.

1. Validate actual configured email/SMS providers; webhook/local HTTP delivery, retries and history are implemented.
2. Expand live evaluation to distractors and insufficient evidence; measure outcomes rather than inventing improvements.
3. Complete clean-setup verification, demo video, slides and submission.

## Boundaries

No automatic production remediation. Lab fault controls affect only this application. Proposed monitor changes require operator review. No arbitrary model-generated shell execution.

Sponsor integrations must have observed evidence. A local fixture mode cannot establish live integration. Keep logs free of credentials and record which data path/model actually handled the work.

## Submission

Deadline: October 27, 2026, 23:45 UTC / 18:45 America/Bogota. Reserve packaging time. See the repository implementation-status guide for current capabilities; this plan includes future work.
