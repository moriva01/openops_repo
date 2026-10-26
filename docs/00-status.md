# Implementation status

## Machine A: monitored host

Validated on Rocky Linux 9.8, Python 3.9.25 and systemd. TeleMediation Convergent runs its API, mediation and delivery as separate services, with SQLite application state. Voice/SMS/data are synthetic usage records, not live telecom traffic. Convergence means a common usage schema and subscriber-level aggregation; it never adds seconds to bytes.

The original collector runs every 15 seconds: CPU, memory, root filesystem usage, uptime, load average, three systemd service states and application telemetry. Its SQLite spool holds at most 1440 samples. At capacity it drops the oldest pending events and logs `retention_dropped`; this is bounded retention, not lossless storage.

## Machine B: monitoring center

Windows with Docker Desktop/WSL2. It runs independent PostgreSQL storage, an authenticated receiver, the portal and evaluator. Zetaris queries a read-only database view. Monitor evaluation uses Zetaris; charts read PostgreSQL directly. A failed Zetaris query does not silently fall back to PostgreSQL.

The default monitor detects VOICE output pending > 0 for 60 seconds and recovers after two distinct healthy samples. The console creates multiple host-scoped monitors with names, metrics, above/below comparisons, severity thresholds, duration, recovery and enablement. Severity escalates and de-escalates with distinct observations. Monitors can be deleted while history remains, provided no active incident exists.

The real two-machine test opened an alert, acknowledged it without resolving it, and resolved it after the output recovered. See `apps/openops/VALIDATION.md`. Private screenshots and credentials are excluded from the repository.

## AI and remaining work

OpenOps now calls Nightshift from its investigation worker, with an injected generator, tool selection, report validation and critique. It implements persistent WorldStoreService, IngestPipelineService and ContextBuilderService from the minimal World Model reference architecture. Advanced engine features are explicitly excluded in the run manifest. See [the integration guide](10-ai-investigation.md).

Password login, admin/manager/operator permissions, user-owned tokens, host/client administration and ticket links are implemented. Opt-in webhook, generic SMS gateway and SMTP connectors use a durable outbox. Remaining work: incident correlation, escalation policies, TLS, broader provider validation and production hardening. See [console guide](11-console-and-administration.md). The platform does not automatically repair application services.

The product name and commercial assumptions remain proposals. No production telecom-interface compatibility is claimed.
