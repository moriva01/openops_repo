# OpenOps Evidence

English presentation content and speaker notes. Review draft.

## 01 OpenOps Evidence

OpenOps Evidence

Evidence-backed incident investigation

Linux monitoring with operator-reviewed AI explanations

Ivan Moreno  
Solo builder

### Speaker notes

OpenOps Evidence is an original monitoring and incident investigation prototype. Ivan Moreno built the solo submission. The demonstration uses synthetic telecom usage records and actual Linux host telemetry. Introduce the product through the operator problem rather than a claim of measured savings.

Sources: README.md; apps/openops/PROJECT_BRIEF.md; docs/01-architecture.md

## 02 A healthy process can still fail delivery

The process is running.  
The VOICE queue keeps growing.

An operator must connect application state with the incident timeline before choosing a response.

INTENDED USERS

Linux operations teams  
  
Managed service providers

Commercial hypothesis: less manual evidence gathering during incident triage.

### Speaker notes

The intended users are small operations teams and managed service providers running Linux applications. The live scenario demonstrates a service that remains active while its VOICE output is disabled. A process-up check cannot explain the queue. Operators need application configuration, queue behavior and host health together. Reduced investigation effort is a product hypothesis, not a measured result.

Sources: apps/telemediation-convergent/telemediation/core.py; docs/10-ai-investigation.md

## 03 The VOICE incident workflow

01  Fault

Disable VOICE output and send synthetic telecom records.

02  Detection

Sustained backlog opens an alert. AI examines incident evidence.

03  Response

Review hypotheses, acknowledge and link an existing ticket.

04  Recovery

Restore output. Healthy samples close alert and trigger recovery webhook.

### Speaker notes

In the demonstration, the operator disables VOICE output and sends synthetic voice, SMS and data records. The default monitor evaluates voice pending above zero sustained for 60 seconds. The collector samples every 15 seconds. Allow roughly 90 seconds in the lab for the sustained condition to appear, rather than claiming fixed detection latency. An acknowledgement links an existing external ticket and does not resolve the alert. Re-enabling VOICE drains the queue, and two distinct healthy samples resolve the alert and enqueue a recovery notification.

Sources: docs/07-testing-and-troubleshooting.md; docs/12-webhook-circuit-demo.md; docs/13-outgoing-webhooks-and-teams.md; apps/openops/receiver/monitor_logic.py

## 04 Deployment across two machines

Machine A  /  Linux

TeleMediation services and SQLite  
Collector with durable telemetry spool

Machine B

Windows Docker: OpenOps, PostgreSQL, Zetaris  
Windows native: Meterless Nightshift

Hosted generation

NVIDIA model calls through Nightshift  
No local GPU required

Data path: collector HTTP ingestion, storage, Zetaris queries, incident analysis, notification outbox.

### Speaker notes

Machine A is the separate Linux monitored node. TeleMediation runs API, mediation and delivery systemd services on Python 3.9+. Its collector samples host and application state and uses a durable SQLite spool. Machine B is Windows with Docker Desktop. OpenOps receiver, evaluator and PostgreSQL run in containers. Zetaris runs its own separate containers and metastore. Nightshift runs natively on Windows and routes generation to hosted NVIDIA. The ingestion API is port 8096, TeleMediation UI/API is 8095, Zetaris UI is 3000 and Nightshift Runtime is 8088. The OpenOps database stays private on the Docker network. Monitors and investigators query the registered view through Zetaris. Portal charts independently read stored PostgreSQL telemetry.

Sources: docs/01-architecture.md; docs/02-infrastructure.md; docs/05-connections-and-credentials.md

## 05 Sponsor technology in the execution path

Zetaris

Registered SQL evidence view for monitors and investigation tools.

Meterless

Persistent World Model adaptation and Nightshift generation runtime.

NVIDIA

Hosted Nemotron generation for planning, investigation and critique.

Current scope: one registered telemetry view. Portal charts read stored PostgreSQL telemetry directly.

### Speaker notes

Zetaris serves the registered read-only openops_pg.monitor_samples view for monitor evaluation and investigation tools. This demonstration has one registered data source, not demonstrated federation across independent external systems. Charts use PostgreSQL directly, as disclosed. The World Model is a minimal adaptation of the Meterless reference architecture implementing WorldStoreService, IngestPipelineService and ContextBuilderService. Nightshift handles the bounded generation roles and retains routed provider receipts. NVIDIA Nemotron supplies actual hosted generation. Requested model names alone are not proof of routed providers; inspect receipts in a completed run.

Sources: docs/10-ai-investigation.md; apps/openops/receiver/zetaris.py; apps/openops/receiver/world_model.py; apps/openops/receiver/nightshift.py

## 06 A bounded investigation with inspectable evidence

Planner

Selects approved evidence tools for the incident context.

Investigator

Compares observations and cites support for each hypothesis.

Evaluator

Reviews support and can request one revision or flag uncertainty.

200 seconds per attempt     5 model calls maximum     3 evidence queries maximum

Reports retain source IDs, execution traces and provider receipts. Operators control any repair.

### Speaker notes

The planner selects tools from a closed list. The implementation also applies an explicit required-evidence policy, so not every choice is model autonomous. Fixed SQL tools retrieve at most three evidence queries in a bounded host/time window. The World Model maintains stable source-linked observations and isolated incident contexts. The investigator proposes hypotheses and alternatives, while the evaluator checks support and can request one revision. Structural citation validation ensures source IDs exist, but it cannot prove factual entailment. A report can be insufficient_evidence or needs_review. At most five model calls and one revision fit a 200-second attempt budget. Provider timeouts and interrupted runs stay explicit. No remediation executes.

Sources: docs/10-ai-investigation.md; apps/openops/receiver/investigation_engine.py

## 07 An operations workspace for the full incident

Host health  
and queue history

Configurable monitors  
  
Alert acknowledgement  
and ticket references  
  
Role-based administration

### Speaker notes

This is an actual screenshot captured from the running reinstalled OpenOps portal after the participant completed the incident and recovery tests. It shows one reporting host, application up and no active alerts. Account identity and the host address/client metadata are hidden in this screenshot. Navigation includes Overview, Monitors, Alerts, Activity and Admin. Roles are admin, manager and operator. Admin controls users, clients, hosts, ticket servers, user-owned tokens and connectors. Generic webhook and Teams notifications support opening and recovery. The screenshot is a lab snapshot, not evidence of production scale.

Sources: assets/overview.png, captured 26 October 2026 America/Bogota; apps/openops/receiver/index.html; docs/11-console-and-administration.md

## 08 An explanation linked to source observations

Observed symptom

VOICE output backlog

Supporting evidence

Output disabled while application processes remain active

### Speaker notes

This screenshot is an excerpt of a completed historical VOICE investigation from the running reinstalled portal. It proposes disabled VOICE output as a supported hypothesis while the application and mediation processes remain active. The report cites immutable observation IDs. The visible high-confidence label is model output, not calibrated accuracy or causal proof. Alternative explanations, missing evidence, recommended checks, evaluator verdict and receipts remain inspectable in the full portal report. The participant confirmed the real provider investigation and recovery circuit during reinstall testing. No new investigation was triggered to produce this image.

Sources: assets/investigation.png, captured from the actual completed report; docs/10-ai-investigation.md

## 09 Reproduction and validation evidence

LIVE INSTALLATION

Fresh repository checkout  
Linux telemetry and real AI analysis  
External webhook and recovery  
Persistent configuration and history

OFFLINE JUDGING

Three deterministic synthetic cases  
Blocked output, CPU pressure,  
insufficient evidence  
Ten offline regression tests

Restart caveat: wait for Zetaris readiness, then restart receiver. Automatic recovery still needs improvement.

### Speaker notes

The participant performed a fresh Windows deployment from public repository commit a2ebf74 and used a newly installed Linux VM. They confirmed host telemetry, the portal, real AI investigation, outbound webhook, client and ticket-server configuration, and alert recovery. The container restart test reached healthy Zetaris state and resumed evaluation after a manual receiver restart. This is participant-reported end-to-end validation plus inspected logs, not an independently rerun production certification. Root offline examples have three deterministic synthetic cases and ten standard-library tests in the recorded validation. These scripted cases do not call live sponsor services and are not a live model-accuracy benchmark. Previously recorded backend tests are documented separately; do not imply all tests were rerun during deck creation.

Sources: docs/08-operations-and-migration.md#windows-restart-order; docs/15-offline-examples.md; tools/verify_examples.py; tests/test_samples.py; participant reinstall and restart results, 26 October 2026

## 10 A product hypothesis for operations teams

An incident record connects the alert,  
source evidence and operator decision.

Product distinction

Deterministic alert lifecycle with a reviewed, cited explanation.

Commercial hypothesis

Hosted or self-managed monitoring for small Linux operations teams.

### Speaker notes

These are proposed product positioning and target users, not measured business outcomes or claims of novelty against named competitors. The differentiation combines deterministic alert transitions, bounded evidence gathering, persisted incident context, evaluator feedback and an inspectable delivery history in one small deployment. Operators can inspect what supports an explanation before choosing any repair. The initial commercial hypothesis is a hosted or self-managed service for small Linux operations teams and managed service providers. No pricing, paying customers, measured time savings or production-scale claims have been established. A pilot should measure time to a useful explanation, unsupported assertions and notification delivery, using predeclared criteria.

Sources: apps/openops/PROJECT_BRIEF.md; docs/14-submission-readiness.md; docs/10-ai-investigation.md

## 11 Pilot priorities and current boundaries

NEXT IMPLEMENTATION

Automatic Zetaris reconnection  
  
Independent evidence connector  
  
Tenant isolation and load testing

PILOT MEASUREMENT

Time to useful explanation  
  
Unsupported-claim rate  
  
Notification delivery reliability

Current boundary: hypotheses for human review. No automatic repairs or established production scale.

### Speaker notes

The prototype already supports multiple host records but the reproduced live demonstration uses one monitored host. Broader testing is future work. Priority one is automatic Zetaris session recovery and dependency readiness. A later pilot can add an independent evidence system such as an external ticket API instead of only storing ticket references. Tenant isolation, provider security hardening and delivery load tests remain production work. Evaluate investigation usefulness with a larger labeled incident corpus and human review. The project does not execute autonomous remediation, has not proven causal correctness and has no established production scale or measured time savings. These boundaries should remain visible in a standalone deck.

Sources: docs/08-operations-and-migration.md; docs/10-ai-investigation.md; docs/14-submission-readiness.md

## 12 A reproducible incident, ready for review

github.com/moriva01/openops_repo

Offline examples

python run.py --sample --all

Live evaluation

Two-machine setup, real sponsor calls and complete alert recovery

### Speaker notes

Close by inviting judges to inspect the repository, reproduce the synthetic offline examples and follow the two-machine installation guides for the real sponsor-backed workflow. Offline mode uses scripted responses and SQLite. It does not replace live sponsor validation. For the live demonstration, show the VOICE fault, sustained alert, real provider-backed investigation, outgoing webhook and healthy recovery. Credentials and signed webhook URLs must remain private. The repository contains the English source, installers, architecture, usage guides and example traces. The deck is a local review draft until the participant approves publication.

Sources: https://github.com/moriva01/openops_repo; README.md; docs/03-monitored-machine-installation.md; docs/04-monitoring-center-installation.md; docs/15-offline-examples.md
