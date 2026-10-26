# Install machine B: Windows monitoring center

## Prerequisites

Install Docker Desktop, enable its WSL2 backend and start Docker. Install Git and Python for preparation scripts. If `python` invokes the Microsoft Store alias, use your installed interpreter (`py` or its full path).

```powershell
docker version
docker compose version
wsl --status
docker info --format '{{.NCPU}} CPUs / {{.MemTotal}} bytes'
```

The Docker server must answer, not just its client. Ubuntu is not required for Docker's internal WSL2 distribution. Provider bash scripts need a compatible shell: the lab used Git Bash for preflight/verify and Windows Compose. For another deployment, follow the provider's Windows/WSL instructions.

## Zetaris: external product

1. Register at https://cloud.enterprise.zetaris.com/register .
2. Download `zetaris-platform.zip` from Run locally: https://cloud.enterprise.zetaris.com/dashboard/download .
3. Extract outside the repository, for example `C:\OpenOps\zetaris-platform`.
4. Execute your account's registry-login command locally. Never paste it into chats or commits.
5. Review the provider's private `.env` and configure the administrator **before first startup**. Preserve the other supplied settings. Do not use its public-server configuration on a laptop without reviewing resources.
6. Run `preflight.sh` in bash from the provider directory, then:

```powershell
docker compose pull
docker compose up -d
```

7. Run `verify.sh` in bash. `init` and `bootstrap` must finish with exit 0; long-running services should be healthy. Initial download and sample loading may take several minutes.

Open http://localhost:3000 . The bundle, credentials, `.env` and driver are not redistributed here. Official reference: https://github.com/zetaris/getting-started . Container names match the validated bundle; explicitly adapt scripts if a provider release changes them.

## New OpenOps installation

From checkout `apps/openops`:

```powershell
python scripts/prepare_receiver.py --platform-env "C:\OpenOps\zetaris-platform\.env" --bind-ip 192.168.1.17 --host-id tmc-lab-01
docker compose up -d --build
```

Preparation is independent of the original checkout location. It generates random private credentials in `.env` and `.local`, preserving existing files. Alternatively, create `.local/zetaris.env` from `zetaris.env.example` using your existing login, then run preparation without `--platform-env`.

If the Zetaris password changed through its UI after initialization, the provider `.env` may be outdated. Privately update `.local/zetaris.env`; never print it.

Attach the driver to the private data network:

```powershell
docker network connect openops_default zetaris-driver-1
```

Do not repeat if already attached. `scripts/start_monitoring.ps1` starts the stack and checks this attachment. Recreating the Zetaris driver requires restoring it. PostgreSQL does not need a LAN port.

Register and verify the datasource:

```powershell
docker compose exec -T receiver python -m receiver.setup_data
docker compose ps
Invoke-RestMethod http://192.168.1.17:8096/health/ready
```

`setup_data` provisions a view and read-only user in **our** database, checks SELECT 1/discovery through Zetaris, and registers `openops_pg.monitor_samples`. The connection is JDBC to our PostgreSQL; telemetry is not written to Zetaris's metastore. Before connecting A, empty data is normal: the monitor reports no-data, not an application failure.

Apply the Windows firewall rule and transfer collector connection settings through SCP. Then:

```powershell
python scripts/receiver_status.py
python scripts/prepare_portal.py
```

Operator access is written privately to `.local/portal-access.txt`. Open http://192.168.1.17:8096 and enter that token. It is separate from TeleMediation and ingestion credentials.

## Nightshift and NVIDIA: separate preparation

Obtain Nightshift Windows at https://meterless.ai/ and complete verification. In Setup -> Providers -> NVIDIA, enter the provider key. Select an available model in Night/Lanes. Console supplies the Runtime URL and access token, separate from the NVIDIA key.

Local diagnostics without displaying secrets:

```powershell
& "$env:LOCALAPPDATA\Nightshift\cli\ns.cmd" status --json
& "$env:LOCALAPPDATA\Nightshift\cli\ns.cmd" discover --json
```

A healthy runtime or model catalog does not prove generation. Run a real text request and check its receipt's routed model. OpenOps now calls Nightshift and persists a minimal World Model. Follow [AI integration setup](10-ai-investigation.md), including `prepare_nightshift.py`, receiver rebuild and datasource-view refresh. Do not put NVIDIA keys in OpenOps `.env` or on A.
