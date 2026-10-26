# Outgoing webhooks and Microsoft Teams

## Configure from the console

Sign in as admin and open **Admin → External connectors → Add connector**. Configuration uses named fields rather than raw JSON:

1. Enter a connector name.
2. Select **Webhook (JSON POST)** for an application's OpenOps JSON endpoint, or **Microsoft Teams (Workflow / Adaptive Card)** for a Teams Workflow webhook.
3. Paste the complete destination in **Webhook URL**. Preserve signed URL query parameters exactly. Teams requires HTTPS.
4. For a signed Teams Workflow URL, leave Bearer token empty unless that endpoint explicitly requires an additional credential.
5. Enable delivery and save.
6. Select **Test** in the connector row. Inspect **Activity → Notification deliveries** for its status and HTTP response code.

The test is visibly marked `TEST` and states that no incident was opened or resolved. It enters the same durable notification outbox as normal deliveries without creating a monitor, alert or fake production telemetry. The connector must be enabled to test it.

## Normal incident notifications

Enabled connectors automatically receive new alert opening, severity-change and recovery transitions. Existing historical alerts are not replayed on enablement. Recovery uses `action: resolved` and `severity: clear`; it is a notification of verified healthy observations, not a remote reset command.

Generic webhooks receive the OpenOps JSON event. Teams receives an Adaptive Card inside the `type: message` envelope, using `application/vnd.microsoft.card.adaptive`. Cards distinguish **ALERT**, **RECOVERED** and **TEST**, and include alert ID, transition, severity, display host name, monitor and selected source evidence. Raw infrastructure identity and full telemetry are not included in Teams cards. The schema follows [Microsoft's Adaptive Card webhook documentation](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/connectors-using#send-adaptive-cards-using-an-incoming-webhook).

Teams Workflows must be configured to post received cards to the intended chat/channel. HTTP 202 establishes acceptance by Power Automate; downstream posting can fail separately. Confirm the resulting card in Teams or inspect the flow run history. Tenant-restricted OAuth triggers require a separate identity integration; a signed URL is appropriate only for a workflow configured to accept it.

## Endpoint protection and editing

Entire webhook URLs, including query signatures, are encrypted at rest with Fernet. API responses return only `has_url`, not the saved URL. Editing shows an empty password-style URL field; leaving it blank preserves the saved destination. Enter a replacement to change it. Bearer and SMTP credentials remain separately encrypted.

Existing endpoint URLs are migrated from readable connector JSON into encrypted storage at startup, preserving destinations. Keep the private encryption secret and database backups together under restricted access. URLs, signatures and credentials must remain outside Git, documentation and shared screenshots. Logs and delivery history record identifiers/statuses without endpoint credentials.

The notification sender rejects redirects and retains retry history. HTTP success codes are stored in `response_status` and shown in Activity. At-least-once delivery and destination-side deduplication requirements still apply.

## Validated lab result — 26 October 2026

The provided private Workflow URL was configured through the actual GUI as **Teams Operations** (connector 3). It remains enabled for future opening and recovery notifications. Its signed URL is not included in this document.

GUI validation confirmed creation, empty-field editing without losing the destination, absence of the URL/signature from admin responses and no JavaScript errors. The console's Test action queued delivery 3. Power Automate returned HTTP **202** on the **first attempt**. The participant confirmed the **TEST - OpenOps connector** card appeared in the configured Teams destination.

41 automated tests passed, covering prior circuit behavior, Teams opening/recovery card structure, marked tests, HTTP acceptance, encrypted endpoint storage, endpoint-preserving edits, legacy endpoint migration and test outbox isolation. The earlier real VOICE incident remains documented in [the local circuit validation](12-webhook-circuit-demo.md); that incident used the local webhook inbox, while this validation confirms a Teams connection test.
