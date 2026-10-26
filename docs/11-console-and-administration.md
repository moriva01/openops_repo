# Operations console and administration

## First login

Start the receiver and wait for `/health/ready`. From `apps/openops`, run `python scripts/prepare_portal.py`. Open the private `.local/admin-access.txt` file locally. Sign in at `http://192.168.1.17:8096` using username `admin` and its generated password. No other production users are created. Use **Account** to change the initial password; the initial note then becomes obsolete. Existing installations retain their data and collector credential.

Passwords require 12–256 characters and use PBKDF2-HMAC-SHA256 with 600,000 iterations and per-user random salts. Sessions expire after eight hours. Cookie sessions are HttpOnly and SameSite=Strict. Mutations require the application header and reject conflicting Origin headers. Failed logins are limited to eight per username/IP pair in 15 minutes. The lab runs HTTP; TLS termination remains deployment work.

## Permissions

| Capability | Admin | Manager | Operator |
|---|---|---|---|
| Overview, host selection and charts | Yes | Yes | Yes |
| Alert details, acknowledge/unacknowledge and ticket links | Yes | Yes | Yes |
| Start and inspect AI investigation | Yes | Yes | Yes |
| System activity and delivery history | Yes | Yes | Yes |
| Create, edit, enable, disable and delete monitors | Yes | Yes | No |
| Users, tokens, hosts, clients, ticket servers and connectors | Yes | No | No |
| Change own password | Yes | Yes | Yes |

The API enforces authorization independently of navigation visibility. Roles apply across the workspace; clients organize hosts without tenant isolation. At least one enabled administrator must remain. Disabling a user invalidates sessions and makes their tokens unusable. Password changes invalidate sessions. User retirement preserves audit identity.

## Independent sections

**Overview** selects one host or all hosts. Cards summarize reporting hosts, active alerts, reachable applications and critical alerts. Host cards display CPU, memory, disk utilization and collected disk path, load averages, observation time and application reachability. Chart series retain host identity. Missing/stale observations produce no-data rather than an application-up claim. The collector reports one disk path per deployment, configured by `COLLECTOR_DISK_PATH` (default `/`).

**Monitors** creates multiple host-scoped conditions. Set a name, metric, above/below comparator, sustained duration, distinct healthy recovery count and severity thresholds. Metrics include CPU, memory, disk, voice/SMS/data output queues, oldest pending age, application reachability and three service process states. Boolean availability metrics use 1 for unavailable and 0 for healthy.

Levels are `info`, `warning`, `minor`, `major`, `critical`. Above thresholds strictly increase with severity; below thresholds strictly decrease. The highest crossed severity applies. Open alerts escalate or de-escalate on distinct fresh observations without duplicate incidents. Transitions are recorded. `clear` follows verified recovery. No-data is a source state. Active incident conditions cannot be redefined or deleted; enablement can still change. Deleted monitors retain historical alerts.

**Alerts** defaults to active incidents and can show all, resolved or unacknowledged incidents. Rows show ID, host, colored severity, acknowledgement, message/reason and ticket. Select several active alerts for shared acknowledgement/ticket assignment. Acknowledgement does not resolve an incident and can be removed. Ticket references link to existing tickets; no external ticket is created. Details contain source evidence and that alert's investigation selector, reports, evaluator verdicts, receipts and traces.

**Activity** combines user actions, administration, alert transitions, bounded receiver logs and notification outcomes. Lists are bounded; PostgreSQL retains audit history. Secrets and password hashes are excluded from responses.

**Admin** contains these tabs:

- **Users:** create accounts, assign roles, reset passwords and enable/disable users. Only admin exists initially.
- **Access tokens:** issue, reassign, expire and revoke user-owned credentials. Tokens inherit the owner's current role. Plaintext appears only at creation; stored values are SHA-256 digests. Reassignment immediately changes effective permissions.
- **Monitored hosts:** register a stable collector ID, display name, IP/DNS address and optional client. Issue or rotate an ingestion token. Configure collector identity, destination and token on that server. Registration does not install software or configure firewalls. Retire monitors before retiring a host.
- **Clients:** manage customer/organization labels associated with monitored hosts.
- **Ticket servers:** name a service and set its browse base URL. For example, `https://example.atlassian.net/browse` with `OPS-123` produces `/browse/OPS-123`. Disabled entries disappear from new acknowledgements; stored links remain.
- **External connectors:** configure webhook, generic SMS HTTP gateway or SMTP email delivery. New connectors start disabled. Enable after configuring the intended destination. Retirement disables delivery and preserves history.

## Connector contracts

Enabled connectors receive new opening, severity-change and recovery events. Enabling a connector does not replay historical events. The durable outbox allows five attempts with bounded exponential delay. Delivery is at least once; HTTP receivers should deduplicate `Idempotency-Key: openops-delivery-<delivery-id>`. Redirects are rejected. Disabling a connector cancels queued deliveries when claimed; in-flight requests can finish.

Webhook configuration:

```json
{"url":"https://example.com/webhook"}
```

JSON POST schema `openops.notification.v1` includes event/alert ID, action, severity, monitor, host and evidence. Optional Secret becomes a Bearer credential.

SMS configuration:

```json
{"url":"https://example.com/sms-gateway","to":"+10000000000"}
```

This uses a generic JSON gateway contract `{to,message,event}`. Use an adapter for providers expecting another schema. Secret becomes Bearer authentication. Real SMS requires provider and recipient configuration.

Email configuration:

```json
{"host":"smtp.example.com","port":587,"username":"alerts@example.com","from":"alerts@example.com","to":"ops@example.com"}
```

SMTP always uses STARTTLS with certificate validation. Secret supplies the optional SMTP password. Credentials belong in Secret, not configuration JSON. Secrets use Fernet encryption with a key derived from private `OPENOPS_ADMIN_TOKEN`. That value is now an internal encryption secret, not a portal credential. Preserve it with backups; rotation requires secret re-encryption.

Installation configures no external recipient. A local HTTP receiver validated webhook delivery. Actual email/SMS provider delivery remains unvalidated until configured.

## API credentials and migration

Login: `POST /api/login`; identity: `GET /api/me`; logout: `POST /api/logout`. Sessions or user-owned Bearer credentials access operational APIs. JSON writes require `X-OpenOps-Request: 1`. Admin resources are `/api/admin/{users,tokens,hosts,clients,ticket_servers,connectors}`. `GET /api/admin` omits credential material.

The original ingestion token stays bound to its original registered host. New hosts receive separate ingestion credentials. Collector credentials never authorize interactive access. The old read token is limited to legacy `/api/hosts` and `/api/events` diagnostics. The old shared admin token no longer grants administration.

Before upgrades, retain a private database dump and preserve `.env`, volumes and host identity. Migrations add tables/columns without discarding telemetry, alerts or reports. Automated tests use temporary schemas and leave no extra production accounts.
