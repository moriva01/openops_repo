# TeleMediation Convergent


This application mediates synthetic usage records, not live telecom traffic. It does not implement SIP, Diameter, SMPP, 3GPP charging interfaces, carrier billing, real calls, real SMS or network convergence. Convergence here means an original common usage schema and subscriber-level view across voice, messaging and data, with unlike quantities kept separate. Subscriber hashes are stable pseudonyms, not anonymization.

## Pipeline

```text
Voice input ----+
SMS input ------+--> durable received queue --> mediation --> output queue
Data input -----+      validation / dedup       normalize        |
                                      routing / reject          v
                                          Voice / SMS / Data output APIs
                                                     |
                                       External consumer polling by cursor
```

Three independent Linux services: `tmc-api`, `tmc-mediation`, `tmc-delivery`. They share a private, WAL-enabled SQLite database. Input is accepted before asynchronous semantic validation; malformed usage enters `rejected` with a reason. Repeating an identical event ID is idempotent. Reusing it with changed content returns 409. Delivery is transactional into a local durable outbox; **delivered means available in that outbox**, not acknowledged by an external billing system. Consumers persist their cursor and handle their own retries.

## Local quick start

Set `TMC_API_TOKEN` to a private random value (24+ characters), then run:

```sh
python3 run.py all
```

Open http://127.0.0.1:8095 and enter the token. The browser holds it in memory only. The dashboard shows process heartbeats separately from processing enablement. It can pause ingress, mediation, delivery or individual portals and create synthetic traffic. Restarting loses no committed records.

Environment: `TMC_DB` defaults to `var/telemediation.sqlite3`, `TMC_PORT` to `8095`, `TMC_BIND` to `127.0.0.1`. `.env.example` documents the variables but is not automatically loaded. For separate local processes, use `python3 run.py api`, `python3 run.py mediation`, `python3 run.py delivery` with identical environment settings.

## Install the packaged app on Linux

Requirements: Python 3.9+, systemd, root installation access. Do not remove or modify existing lab software. This installer uses only its own `/opt`, `/etc`, `/var/lib` directories and three `tmc-*` units; it refuses an existing installation. No packages are installed automatically.

```sh
tar -xzf telemediation-convergent-0.1.0.tar.gz
cd telemediation-convergent
sudo bash scripts/install.sh
sudo systemctl status tmc-api tmc-mediation tmc-delivery
```

The installer generates a private token in `/etc/telemediation-convergent/runtime.env`, readable only by root. Keep it local; do not paste it into chat. Services run as unprivileged `tmc`. Use `journalctl -u tmc-mediation` for structured process logs; record and configuration events are in the durable audit table and API.

Default listener is loopback. Access a remote VM through `ssh -L 8095:127.0.0.1:8095 user@vm-address`. Configure a reviewed TLS reverse proxy or SSH forwarding for permanent remote monitoring; do not expose the bearer API over a public plaintext connection. Firewall, TLS and VM installation are not automatically configured by this package.

## API contract

All endpoints except `/` and `/health/live` require `Authorization: Bearer <TMC_API_TOKEN>`. A single lab token currently grants both read and control access; role separation is future work. API bodies are limited to 64 KiB. No arbitrary shell commands or external URLs are executed.

| Endpoint | Purpose |
|---|---|
| `GET /health/live` | API process liveness |
| `GET /health/ready` | 200 only if all three heartbeats are fresh and processing is enabled; otherwise 503 |
| `GET /api/status` | Process freshness, portal enablement, queues, oldest pending age, throughput, latency |
| `GET /api/records` | Last 100 record states, validation errors and destinations; excludes raw subscriber IDs |
| `GET /api/audit` | Last 100 ingestion, mediation, delivery and configuration events |
| `GET /api/convergence` | Up to 100 grouped subscriber/service/unit totals |
| `POST /api/inputs/{voice,sms,data}` | Ingest one synthetic record |
| `GET /api/outputs/{voice,sms,data}?after=0` | Up to 100 ordered normalized outputs, with durable next cursor |
| `POST /api/settings` | Change a service, portal or route |

Common input fields: `event_id` (globally unique string), `subscriber_id` (synthetic identifier), `occurred_at` (ISO timestamp including timezone). Voice adds non-negative integer `duration_seconds`; SMS adds `message_count`; data adds `bytes_used`.

```json
{"event_id":"example-voice-001","subscriber_id":"synthetic-001","occurred_at":"2026-10-26T12:00:00Z","duration_seconds":60}
```

Normalized `tmc.usage.v1` records have `event_id`, `service_type`, `subscriber_ref` (SHA-256), `occurred_at`, `quantity`, `unit` and input provenance. Output routing does not change service type or units.

Configuration request examples:

```json
{"key":"output.voice","value":false}
```

```json
{"key":"mediation.enabled","value":false}
```

```json
{"key":"route.voice","value":"data"}
```

The last example routes a voice usage record through the data output portal for a routing test; it remains a voice record. This is record routing, not protocol conversion.

## Reproducible monitoring scenarios

Run `python3 scripts/send_traffic.py --batches 30 --interval 1` with the same token exported.

1. Normal: three input channels produce normalized output and a shared subscriber convergence view.
2. Output outage: disable `output.voice`. Voice pending-output count and age grow while SMS/data continue. Re-enable it; queue drains without duplicate outputs.
3. Mediation pause: disable `mediation.enabled`. Input queue grows; process heartbeat stays alive. Re-enable it; processing resumes.
4. Process failure: stop `tmc-mediation`. After 15 seconds its heartbeat becomes stale. Distinguish this from scenario 3.
5. Invalid record: submit a negative duration; mediation rejects it and preserves the error and audit trail.


## Validate and package

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build_package.py
```

The source archive in `dist/` excludes state, secrets, caches and vendor material. It includes source, tests and installer; SHA-256 is emitted alongside it. Local automated tests do not prove installation on a target Linux VM. Check Python version and connectivity there before installing.

## Limitations

Single-node SQLite and a standard-library HTTP server are appropriate for this lab, not a carrier production platform. No TLS termination, rate limiting, RBAC, retention jobs, external delivery acknowledgements, billing, roaming settlement or real telecom protocol adapters. Raw synthetic subscriber IDs remain in the private input database. The all-in-one mode is for development; use separate services to test real process failures. No external alerting or monitoring platform is installed by this project.
