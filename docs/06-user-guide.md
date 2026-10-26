# User guide

## TeleMediation Convergent

Open the :8095 portal and enter the application token. Processing controls pause application logic rather than terminating processes; heartbeats can remain healthy. Input/Output controls enable individual portals.

Send voice, SMS and data records creates one synthetic record per channel. The lifecycle is received -> mediated -> delivered. Invalid usage is rejected with a reason. Identical event-ID/content retries are idempotent; changed content with the same ID conflicts.

Output portals are cursor APIs, not telecom protocol sockets. `GET /api/outputs/voice?after=0` and SMS/data equivalents return up to 100 records with `next_cursor`. Consumers persist their cursor. No external billing-system acknowledgement is recorded.

`GET /api/convergence` groups by subscriber reference and service/unit. A subscriber SHA-256 is a stable pseudonym, not anonymization. Do not use real subscriber records in this lab.

## OpenOps console

Sign in at :8096 with username/password. Export the initial private admin note using `python scripts/prepare_portal.py` after receiver readiness. Only admin exists initially. Use Admin to add other users.

Overview, Monitors, Alerts, Activity and Admin are independent pages. Select one host or all hosts. Monitors support named host conditions and changing severities. Alert details contain acknowledgement/ticket actions and AI investigation. Activity includes user actions, transitions, runtime logs and delivery history.

Follow the complete [console and administration guide](11-console-and-administration.md) for permissions, enrollment, metrics, thresholds, tickets and connectors. Follow [AI investigation](10-ai-investigation.md) for generation budgets and evidence boundaries.
