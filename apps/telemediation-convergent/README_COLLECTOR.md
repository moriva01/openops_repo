# OpenOps collector for TeleMediation

Original Linux collector, Python 3.9+, standard library only. The collector performs measurements; Zetaris and Meterless are planned consumers on the monitoring node, not dependencies of this VM agent. It does not execute AI-generated commands or modify application settings.

## Measurements

- Host aggregate CPU utilization from counter deltas; memory available/used; disk capacity/free; uptime and load average.
- Actual systemd states of the three `tmc-*` application services, even when the HTTP API is down.
- Application API reachability, worker heartbeat ages, processing enabled/disabled, input/output portal state, routes, queued/delivered/rejected counts, oldest pending age, throughput and mean delivery latency.
- Host measurements are real. TeleMediation usage records are synthetic; these are distinct concepts.

CPU's first continuous sample is null because no elapsed counter interval exists yet. Diagnostics wait briefly to measure a delta. All sample timestamps use UTC. Independent monotonic timing controls the loop.

## Install alongside an existing application

Copy `tmc-collector-0.1.0.tar.gz` to the VM. Extract into a fresh directory:

```bash
mkdir -p ~/tmc-collector-install
tar -xzf ~/tmc-collector-0.1.0.tar.gz -C ~/tmc-collector-install
cd ~/tmc-collector-install/telemediation-convergent
sudo bash scripts/install_collector.sh
sudo systemctl status tmc-collector --no-pager
sudo journalctl -u tmc-collector -n 10 --no-pager
sudo python3 scripts/check_collector.py
```

The diagnostic prints telemetry, never credentials. Verify `application.reachable`, process states and portal counts. Installation has not been tested on the user's VM until these checks are run there.

Installer adds only `collector.py`, a `tmc-collector` service and its own config/state directories. It does not restart or rewrite the existing application. Services run as `tmc`. The existing application token is loaded privately by systemd from its root-only environment file. Do not paste it into chat.

## Offline and delivery contract

Samples are collected every 15 seconds and persisted in `/var/lib/tmc-collector/spool.sqlite3`. No monitoring receiver exists yet. With blank destination settings, local collection continues and logs show `destination_configured: false`. This is expected.

The queue retains at most 1440 events (approximately six hours at the default interval). At capacity the oldest pending events are dropped and `retention_dropped` reports the count. This is bounded retention, not guaranteed lossless storage. Outages are retried on subsequent cycles; a failed/uncertain send preserves event IDs for receiver deduplication.

Once the monitoring node is ready, edit `/etc/tmc-collector/collector.env` locally:

```text
COLLECTOR_INGEST_URL=<the monitoring receiver endpoint>
COLLECTOR_INGEST_TOKEN=<separate receiver credential>
```

Use TLS or a private tunnel for transport; no new public port is opened on the VM. Restart `tmc-collector` after configuration. Never reuse the application's control token as the ingestion credential.

Request: authenticated POST, `Authorization: Bearer <ingestion credential>`:

```json
{"schema":"openops.batch.v1","events":[{"schema":"openops.telemetry.v1","event_id":"unique-id","host_id":"tmc-lab-01","observed_at":"UTC timestamp","host":{},"application":{},"systemd_units":{},"collection_errors":[]}]}
```

Receiver must durably store/deduplicate by `event_id` before returning:

```json
{"accepted_event_ids":["unique-id"]}
```

Only explicitly acknowledged events are removed. Batches contain up to 50 samples; HTTP timeout is five seconds, no immediate retry. This provides at-least-once attempts within the bounded retention window. No end-to-end delivery is claimed until the receiver exists and is tested.

## Boundaries

The collector reads Linux host metrics and this application's documented API. No subscriber IDs, usage bodies, tokens or environment snapshots are transmitted. Only the three named systemd units are queried. Arbitrary service discovery, log-file tailing, NIC-level traffic measurement, remote command execution and remedial actions are outside this first version. Access to the telemetry spool is restricted to its service user/root. Hostnames and operational status are part of the telemetry.
