# Webhook opening and recovery circuit

## Local receiver

The optional webhook inbox runs as a separate container on the monitoring machine. OpenOps posts over the private Docker network to `http://webhook-demo:8097/webhook`. The inbox UI binds only to Windows loopback at `http://127.0.0.1:8097`; no external notification service is needed.

From `apps/openops`:

```powershell
python scripts/prepare_webhook_demo.py
docker compose build receiver
docker compose -f compose.yaml -f compose.webhook-demo.yaml up -d --no-deps webhook-demo
```

Preparation preserves an existing private token in `.local/webhook-demo.env`. The matching private access note is `.local/webhook-inbox-access.txt`. The inbox stores durable receipts in its separate `webhook-demo-data` volume. It acknowledges only after SQLite commit. Repeated idempotency keys with matching payloads do not create duplicate receipts; conflicting content is rejected.

## Configure OpenOps

Sign in as admin. Open **Admin → External connectors → Add connector**:

- Name: `Local webhook inbox`.
- Type: `Webhook (JSON POST)`.
- Configuration: `{"url":"http://webhook-demo:8097/webhook"}`.
- Secret: the private `WEBHOOK_DEMO_TOKEN` value.
- Enable delivery: selected.

The connector's credential is encrypted in OpenOps and sent as a Bearer header. Never include it in shared screenshots or reports. Enabling a connector does not replay old alerts.

Open the loopback inbox URL and connect using the same private token. The UI clears the input and retains the credential only in memory. OpenOps **Activity** separately shows outbound delivery status and attempt count.

## Real circuit test

1. Confirm fresh Linux telemetry, healthy Zetaris queries, normal VOICE monitor and running inbox.
2. In TeleMediation on the monitored machine, disable **Output VOICE** and send a synthetic voice/SMS/data batch. Leave other controls unchanged.
3. The Linux application retains a pending VOICE record. Its collector sends real application state through the existing receiver into PostgreSQL.
4. The monitor reads evidence through Zetaris. A sustained violation opens one alert after the configured duration, normally 60 observed seconds.
5. Opening writes an outbox entry in the alert transaction. The notification worker sends `action: opened` with the alert ID and severity. Verify `delivered` in Activity and an authenticated durable inbox receipt.
6. Inspect that alert's automatic AI investigation. It uses Zetaris evidence, shared World Model context and Nightshift generation. A provider failure remains an explicit failure, independent of notification delivery.
7. In OpenOps, acknowledge the alert if desired. Acknowledgement does not clear the failure.
8. Re-enable **Output VOICE**. The application drains its queued record. After two distinct fresh healthy observations, the monitor resolves the same alert.
9. Verify a second inbox event with `action: resolved`, `severity: clear`, the same alert ID and a different event/delivery key. This is the recovery/reset notification; it does not reset the server or execute remediation.
10. Confirm VOICE output remains enabled, queue is empty, monitor is normal and both outbound entries are delivered.

The two-node test uses real application controls and collector telemetry, not injected production alert rows. Inbox unit fixtures remain isolated from the live receipt database. Provider receipts and source event IDs support later inspection without exposing credentials.

## Boundaries

The inbox is a local demonstration destination, not an external team's endpoint. The sender uses at-least-once delivery; the inbox deduplicates retries. The public UI shell does not disclose receipts without authentication. Stored operational payloads remain private. Logs print transition/alert identifiers but never the Bearer token.

Stop only the optional inbox with:

```powershell
docker compose -f compose.yaml -f compose.webhook-demo.yaml stop webhook-demo
```

Disable its connector in Admin before stopping it if future notifications should not retry. Preserve the volume to retain evidence. Do not remove the monitoring database volume.

## Validated live result — 26 October 2026

Connector `Local webhook inbox` (ID 1) delivered the real VOICE incident, Alert 2:

| Transition | UTC time | Delivery | Result |
|---|---|---|---|
| Alert opened | 19:14:19.277 | 1: `opened`, `warning` | Delivered at 19:14:20.750, first attempt |
| Acknowledged by admin | 19:15:31.571 | No recovery notification | Alert remained active |
| Alert resolved | 19:16:34.178 | 2: `resolved`, `clear` | Delivered at 19:16:36.788, first attempt |

Both inbox receipts have alert ID 2 and distinct idempotency keys `openops-delivery-1` and `openops-delivery-2`. Opening source event: `f0f34934-d8dc-4e12-8391-06e2163613a6`. Recovery source event: `8e0dd455-56df-4a40-b550-029d27820161`.

Investigation `inv_3feaa08227e141d782b9e836d890d264` completed on its first attempt. Its cited hypothesis identified disabled VOICE output during the violation; the evaluator returned `supported` with no issues. Nightshift routed planner/investigator/evaluator calls to NVIDIA `nvidia/nemotron-3.5-bolt-e4b`, with receipts `rcpt_req_fsp0x7ve`, `rcpt_req_6bw9ilqg`, `rcpt_req_wl0o8twt`.

Final state: VOICE output enabled, pending output 0, monitor normal, source ok, both deliveries delivered. The system executed no repair; the participant restored output through TeleMediation.

35 automated tests passed. Two targeted inbox tests passed again after correcting numeric-equivalence handling: a JSON retry containing `1` instead of `1.0` is identical, while changing the value to a boolean remains a conflict. A live replay confirmed `inserted:false`, without another receipt. Inbox authentication rejected anonymous receipt access (401). Headless Chrome confirmed the authenticated inbox renders, clears the credential input and has no JavaScript errors. Existing receipts survived inbox-container recreation.
