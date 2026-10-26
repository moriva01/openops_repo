# OpenOps Evidence — agreed product direction

26 October 2026. User approved proceeding with the product direction. This is a build specification, not a claim of completed features.

## Product and buyer

An original operations platform for small IT operations teams and managed service providers. Collect host and application telemetry, configure monitors, manage incident lifecycles, investigate failures with evidence and verify recovery. The initial commercial hypothesis is reduced investigation time; validate it with operators rather than claiming established demand.


## Demo application: job-processing service

A small application accepts synthetic jobs, processes them with a worker, and calls a separate dependency endpoint. It reports queue depth, completed/failed jobs, processing latency, worker heartbeat and dependency health. Host measurements are real and labelled separately from synthetic workload data.

Primary incident: stop the dependency through a documented lab-only fault control. Worker failures increase, throughput drops, backlog grows and latency rises. Record the intervention timestamp as evaluation ground truth, withheld from investigator context. The investigator must find failure evidence and dependency relationships, not read the answer from a scenario label.

Recovery: restore the dependency, verify successful probes, resumed throughput and draining backlog. Resolving the dependency alert does not immediately resolve backlog-related alerts.

## Three evaluation cases

1. Dependency outage: correct suspected cause supported by service probes and worker errors.
2. Distractor: CPU spike on an unrelated service alongside a dependency outage; no false CPU attribution to the affected application.
3. Insufficient evidence: missing dependency observations; explicitly report uncertainty and propose a specific next check.

For each record detection time, investigation time, model calls, cited-source validity, agreement with withheld ground truth and recovery-verification outcome. Maintain a rules-only baseline for comparison. Do not invent percentage improvements.

## Deployment

- Monitoring node: current Windows host, Docker Desktop, working Zetaris stack; separate application PostgreSQL database, API, scheduler and portal; native Nightshift runtime.
- Budget host memory across Docker and VM; the existing 28 GB physical RAM is shared. No assumption of a local GPU.

## Data architecture

Collector sends authenticated, bounded batches to ingestion API; buffer briefly during outages and deduplicate retries by observation ID. PostgreSQL persists normalized telemetry and separate configuration/history tables. Do not use Zetaris's internal metastore or audit databases as application storage.

Register application data sources in Zetaris. Agent retrieval tools use Zetaris to correlate telemetry, app dependencies, rule definitions and incident history. Verify supported SQL/source interfaces before producing registration scripts. Portal and deterministic alert evaluation may access the application database directly; document which paths actually use Zetaris.

Nightshift is the primary model provider. World Model Engine implements stable entity IDs, append-only observations with provenance, idempotent/resumable ingestion and a structured bounded context builder. Investigator and evaluator consume this context. Engine status and implemented/omitted reference features are explicit in each run manifest.

## Required product workflow

1. Register a host and application; show last-seen and telemetry freshness.
2. Configure a monitor with threshold, duration, severity, recovery condition and destination.
3. Open/deduplicate alerts, acknowledge them, retain transition history, resolve only on recovery evidence. Never confuse disabled monitor with resolved alert.
4. Group related alerts into an incident with explainable grouping evidence.
5. Investigator chooses read-only tools based on evidence gaps, maximum 4 tool steps. Collect bounded time ranges and at most 100 records per tool.
6. Evaluator checks citations, alternatives and uncertainty; allow at most one revision. A valid citation is necessary but not sufficient to establish causation.
7. Render timeline, observations, suspected cause, alternatives, missing facts and recommended checks.
8. Deliver a webhook with timeout, deduplication, bounded retries and delivery history. SMTP email is next; SMS and advanced escalation are deferred until the core works.
9. Verify recovery and show whether the incident's user-visible symptoms cleared.

No automatic production remediation. Fault injection controls act only on this project's lab application. Model-generated monitor definitions are drafts requiring operator review, not arbitrary executable commands.

## Portal views


## Implementation order

1. Finish Nightshift connection, model discovery and real response test.
2. Confirm monitored VM and access; inspect OS/network without modifying existing services.
3. Build original app, collector, ingestion API and application DB; prove two-node telemetry.
4. Build monitor lifecycle and portal; demonstrate fault, alert and recovery without model dependency.
5. Connect Zetaris retrieval and World Model; implement bounded investigation/evaluation through Nightshift.
6. Add webhook and measured three-case evaluation.
7. Fresh-setup verification, labelled offline sample mode, public-source review, 1–4 minute video, required slides and submission.

Deadline: 27 October 2026 at 18:45 America/Bogota. Reserve packaging time. If scope must shrink, keep one complete observed incident workflow and remove secondary features first.

## Status

Zetaris: all 9 official verification checks passed in the previous setup turn. Nightshift CLI: installed; local runtime connection refused during this inspection. Application, collector, portal, engine, adapters and evaluations: not implemented yet. Team creation: confirmed by user. This plan supersedes the earlier report-only scope in PROJECT_BRIEF.md.
