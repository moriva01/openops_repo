# Implementation status

## Machine A: monitored host

Validated on Rocky Linux 9.8, Python 3.9.25 and systemd. TeleMediation Convergent runs its API, mediation and delivery as separate services, with SQLite application state. Voice/SMS/data are synthetic usage records, not live telecom traffic. Convergence means a common usage schema and subscriber-level aggregation; it never adds seconds to bytes.

The original collector runs every 15 seconds: CPU, memory, root filesystem usage, uptime, load average, three systemd service states and application telemetry. Its SQLite spool holds at most 1440 samples. At capacity it drops the oldest pending events and logs `retention_dropped`; this is bounded retention, not lossless storage.

## Machine B: monitoring center

Windows with Docker Desktop/WSL2. It runs independent PostgreSQL storage, an authenticated receiver, the portal and evaluator. Zetaris queries a read-only database view. Monitor evaluation uses Zetaris; charts read PostgreSQL directly. A failed Zetaris query does not silently fall back to PostgreSQL.

The default monitor detects VOICE output pending > 0 for 60 seconds and recovers after two distinct healthy samples. The UI edits name, metric, threshold, duration, recovery count and enablement. The API supports severity; the current UI preserves its existing value. Creating additional monitors through the UI is not implemented yet.

The real two-machine test opened an alert, acknowledged it without resolving it, and resolved it after the output recovered. See `apps/openops/VALIDATION.md`. Private screenshots and credentials are excluded from the repository.

## AI and remaining work

Nightshift 1.2.7 answered a separate request using NVIDIA `nvidia/nemotron-3.5-bolt-e4b`. This proves provider connectivity, not AI integration in OpenOps.

Remaining work: implement Meterless World Model Engine, investigation and critique through Nightshift, incident correlation, webhooks/email/SMS, escalation, multiple hosts, RBAC, user authentication, TLS and production hardening. The platform does not automatically repair application services.

