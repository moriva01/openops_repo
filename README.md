# OpenOps — operations lab repository

Original source for **TeleMediation Convergent**, its Linux collector, and the **OpenOps** monitoring platform. This repository documents the implementation as of October 26, 2026. Documentation, application interfaces, examples and installation instructions are in English.

The system uses two independent machines: one runs a synthetic telecom mediation application; the other receives and stores telemetry, queries it through Zetaris, and evaluates monitors. A VM is one deployment option for the first machine, not an architectural requirement.

## Start here

1. [Implementation status and limitations](docs/00-status.md).
2. [System architecture](docs/01-architecture.md).
3. [Requirements, ports and firewall](docs/02-infrastructure.md).
4. [Install the monitored machine](docs/03-monitored-machine-installation.md).
5. [Install the Windows monitoring center](docs/04-monitoring-center-installation.md).
6. [Connections, credentials and queries](docs/05-connections-and-credentials.md).
7. [User guide](docs/06-user-guide.md).
8. [Acceptance tests and troubleshooting](docs/07-testing-and-troubleshooting.md).
9. [Operations, backups and deployment migration](docs/08-operations-and-migration.md).
10. [Repository validation](docs/09-repository-validation.md).
11. [Meterless investigation and shared world state](docs/10-ai-investigation.md).

## Repository layout

```text
apps/
  telemediation-convergent/  Application, collector, installers and package builders
  openops/                  Receiver, PostgreSQL Compose, monitor, portal, Zetaris adapter
docs/                       Deployment and operations guides for both machines
tools/                      Repository checks and setup-script tests
```

Each application retains its technical README, scripts and tests. Planning files in `apps/openops` describe earlier proposals; where they differ, `docs/00-status.md` and the implementation take precedence. `apps/openops/VALIDATION.md` records the real incident test.

## Working features

Real host telemetry; synthetic voice/SMS/data mediation; durable collector spool; authenticated ingestion; independent PostgreSQL storage; a read-only Zetaris datasource; a configurable monitor; charts; and an alert lifecycle with acknowledgement and automatic recovery verification.

AI investigation now retrieves evidence through Zetaris and uses a persistent minimal World Model implementation with planner, investigator and evaluator calls through Nightshift. Reports retain citations, uncertainty and provider receipts. See the integration guide for boundaries and validation. Incident correlation, notifications and automatic remediation remain unimplemented. A resolved alert does not mean the platform performed a repair.

## Excluded material

The repository does not include real credentials, runtime databases, production histories, `.local` files, Zetaris binaries/JDBC drivers or Nightshift installers. Obtain Zetaris and Meterless from their providers. Build our application packages from source.

Consolidating this source does not change running deployment paths. Read the migration guide before operating the existing deployment from this checkout.
