# Requirements, ports and firewall

## Resources

| Machine | Functional requirements | Recommended lab baseline |
|---|---|---|
| A: Linux | Python >=3.9, SQLite JSON functions, systemd, SSH/SCP, sudo for installation | 2 CPUs, 2 GB RAM, 2 GB free for small workloads |
| B: Windows | Docker Desktop with WSL2 backend, Git, Python >=3.9 for helper scripts | Provider guidance suggests at least 16 GB total RAM; prefer 24 GB+ when also hosting A |
| Docker on B | Supplied Zetaris requirements: 4 CPUs, 8 GB assigned RAM, 15 GB free disk | Additional space for images, telemetry and backups |

A's recommendation is guidance, not a capacity benchmark. The validated host had Rocky 9.8, Python 3.9.25, 2 CPUs and approximately 3 GB RAM. Application SQLite and PostgreSQL have no automatic retention implemented; workload determines growth.

The lab Windows computer has approximately 28 GB physical RAM. Docker reported 4 CPUs and 13.6 GB available. A VM on the same host shares those physical resources. Hosted NVIDIA models through Nightshift do not require a local GPU.

## Port matrix

| Source -> destination | TCP | Purpose | Required exposure |
|---|---:|---|---|
| Windows -> Linux | 22 | SSH, SCP, optional tunnel | Administration only |
| Windows -> Linux | 8095 | Direct TeleMediation portal/API | Windows host only; alternatively tunnel |
| Collector -> local Linux API | 8095 | Read `/api/status` | Loopback |
| Linux -> Windows | 8096 | Authenticated ingestion | Firewall restricted to A |
| Windows browser -> Windows | 8096 | OpenOps portal | Shared receiver port |
| OpenOps Docker -> Zetaris UI | 3000 | Login and SQL through UI proxy | `host.docker.internal:3000` |
| Zetaris driver -> OpenOps DB | 5432 | PostgreSQL JDBC | Docker network only, unpublished |
| Windows -> Zetaris API | 8888/8889 | Provider API and diagnostics | Current publication is loopback |
| Windows -> Zetaris driver | 10000 | Optional client JDBC | Loopback; OpenOps does not use it |
| Windows -> Spark UI | 4040 | Provider diagnostics | Loopback |
| Future OpenOps -> Nightshift | 8088 | AI runtime/API | Local; not integrated yet |

Zetaris's internal PostgreSQL is not OpenOps storage. Random provider diagnostic ports are not stable integration addresses.

## Network addressing

With bridged networking, A and B must communicate on the LAN. B's LAN interface is `192.168.1.17`, not `192.168.56.1` or a WSL/Hyper-V address. Reserve addresses through DHCP or update configuration when they change. Containers use their own Docker network.

## Linux firewall for direct portal access

The installer defaults to loopback. To permit access from B:

```bash
sudo sed -i 's/^TMC_BIND=.*/TMC_BIND=0.0.0.0/' /etc/telemediation-convergent/runtime.env
sudo systemctl restart tmc-api
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="192.168.1.17/32" port port="8095" protocol="tcp" accept'
sudo firewall-cmd --reload
```

This assumes active firewalld and the default zone. For custom zones, inspect `--get-active-zones` and choose the correct `--zone`. Do not open the port globally. The collector needs no inbound port.

Without publishing 8095, run on B: `ssh -N -L 8095:127.0.0.1:8095 labadmin@192.168.1.202`, then open `http://localhost:8095`.

## Windows firewall

Run in Administrator PowerShell:

```powershell
New-NetFirewallRule -DisplayName "OpenOps receiver from monitored VM" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8096 -LocalAddress 192.168.1.17 -RemoteAddress 192.168.1.202 -Profile Any
```

`apps/openops/scripts/allow_vm_firewall.ps1` also checks for an existing rule. These examples use lab addresses; review them for another network.

Do not forward ports on the router. Lab HTTP does not encrypt tokens or telemetry; use TLS or a tunnel outside a trusted network. These applications do not implement TLS termination yet.
