# Requisitos, puertos y firewall

## Recursos

| Máquina | Requisitos funcionales | Base recomendada de laboratorio |
|---|---|---|
| A: Linux | Python >=3.9, SQLite con JSON, systemd, SSH/SCP, sudo para instalar | 2 CPU, 2 GB RAM, 2 GB libres para aplicación/datos pequeños |
| B: Windows | Docker Desktop con backend WSL2, Git, Python >=3.9 para scripts auxiliares | 16 GB RAM total como mínimo práctico del proveedor; preferible 24 GB+ si también aloja A |
| Docker de B | Requisitos Zetaris suministrados: 4 CPU, 8 GB RAM asignada, 15 GB libres | Más espacio para imágenes, telemetría y respaldos |

La recomendación de A es orientativa, no un benchmark de capacidad. Se validó Rocky 9.8 con Python 3.9.25, 2 CPU y aproximadamente 3 GB de RAM. La app y el recolector son ligeros, pero SQLite de aplicación y PostgreSQL no tienen limpieza automática implementada. El volumen de tráfico determina el crecimiento.

El equipo Windows del laboratorio tiene aproximadamente 28 GB RAM física; Docker reportó 4 CPU y 13,6 GB disponibles. Compartir host con una VM consume los mismos recursos físicos. No hace falta GPU local para usar modelos NVIDIA alojados mediante Nightshift.

## Matriz de puertos

| Origen -> destino | TCP | Uso | Exposición necesaria |
|---|---:|---|---|
| Windows -> Linux | 22 | SSH, SCP, túnel opcional | Solo administración |
| Windows -> Linux | 8095 | Panel/API TeleMediation directo | Solo Windows; alternativa túnel |
| Recolector -> API local Linux | 8095 | Leer `/api/status` | Loopback |
| Linux -> Windows | 8096 | Ingesta autenticada | Firewall solo IP de A |
| Navegador Windows -> Windows | 8096 | Portal OpenOps | Mismo puerto que ingesta |
| OpenOps Docker -> Zetaris UI | 3000 | Login y SQL por UI proxy | `host.docker.internal:3000` |
| Zetaris driver -> OpenOps DB | 5432 | JDBC PostgreSQL | Solo red Docker; no publicado |
| Windows -> Zetaris API | 8888/8889 | API del proveedor, diagnóstico | Publicación actual en loopback |
| Windows -> Zetaris driver | 10000 | JDBC cliente opcional | Loopback; OpenOps no lo usa |
| Windows -> Spark UI | 4040 | Diagnóstico proveedor | Loopback |
| OpenOps futuro -> Nightshift | 8088 | Runtime/API IA | Local; aún no integrado |

PostgreSQL interno de Zetaris no es la base de OpenOps. Los puertos aleatorios de diagnóstico del proveedor no deben reutilizarse ni asumirse estables.

## Red entre máquinas

Con adaptador puente, A y B deben comunicarse en la LAN. La interfaz LAN de B es `192.168.1.17`, no `192.168.56.1` ni las interfaces WSL/Hyper-V. Reservar IP por DHCP o actualizar configuraciones si cambia. Docker utiliza su propia red para los contenedores.

## Firewall Linux para acceso directo al panel

La instalación original escucha en loopback. Para permitir acceso desde B:

```bash
sudo sed -i 's/^TMC_BIND=.*/TMC_BIND=0.0.0.0/' /etc/telemediation-convergent/runtime.env
sudo systemctl restart tmc-api
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="192.168.1.17/32" port port="8095" protocol="tcp" accept'
sudo firewall-cmd --reload
```

Esto asume firewalld activo y la interfaz en su zona predeterminada; con zonas personalizadas use `--get-active-zones` y seleccione la correcta con `--zone`. No abra el puerto globalmente. El recolector no necesita puertos entrantes.

Alternativa sin publicar 8095: desde B `ssh -N -L 8095:127.0.0.1:8095 labadmin@192.168.1.202`, abrir `http://localhost:8095`.

## Firewall Windows

En PowerShell como administrador:

```powershell
New-NetFirewallRule -DisplayName "OpenOps receiver from monitored VM" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8096 -LocalAddress 192.168.1.17 -RemoteAddress 192.168.1.202 -Profile Any
```

También existe `apps/openops/scripts/allow_vm_firewall.ps1`, con comprobación de regla existente. Los ejemplos están fijados a las IP del laboratorio: revíselos antes de usarlos en otra red.

No abrir puertos en el router. El transporte HTTP de este laboratorio no cifra tokens ni telemetría; en una red no confiable se requiere TLS o túnel. No se ha implementado terminación TLS en estos aplicativos.
