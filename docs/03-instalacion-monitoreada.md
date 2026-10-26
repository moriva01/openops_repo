# Instalar máquina A: TeleMediation y recolector

## Comprobar Linux

```bash
cat /etc/os-release
python3 --version
command -v systemctl
python3 -c 'import sqlite3; print(sqlite3.connect(":memory:").execute("SELECT json_extract(?,?)", ("{\"ok\":1}","$.ok")).fetchone())'
```

Se necesita Python >=3.9 y SQLite JSON. Si falta, instale un intérprete compatible con los repositorios de su distribución; no sustituya a ciegas el Python que usan herramientas del sistema. Los instaladores comprueban requisitos y no instalan paquetes automáticamente.

## Generar paquetes desde el repositorio

En Windows o Linux con Python, desde `apps/telemediation-convergent`:

```text
python scripts/build_package.py
python scripts/build_collector.py
```

Se generan `dist/telemediation-convergent-0.1.0.tar.gz`, `dist/tmc-collector-0.1.0.tar.gz` y sus SHA-256. Los scripts excluyen claves, estado y código de terceros.

Desde Windows, ajustando la ubicación del checkout:

```powershell
$repo = "C:\OpenOps\openops_repo"
scp "$repo\apps\telemediation-convergent\dist\telemediation-convergent-0.1.0.tar.gz" "$repo\apps\telemediation-convergent\dist\tmc-collector-0.1.0.tar.gz" labadmin@192.168.1.202:~/
```

## Aplicación

En Linux:

```bash
mkdir -p ~/tmc-app-install
tar -xzf ~/telemediation-convergent-0.1.0.tar.gz -C ~/tmc-app-install
cd ~/tmc-app-install/telemediation-convergent
sudo bash scripts/install.sh
sudo systemctl status tmc-api tmc-mediation tmc-delivery --no-pager
curl http://127.0.0.1:8095/health/live
```

Instala código en `/opt/telemediation-convergent`, estado en `/var/lib/telemediation-convergent/state.sqlite3` y configuración privada en `/etc/telemediation-convergent/runtime.env`. Los servicios corren como `tmc`, no como root. Código, base y nombres son independientes de software anterior.

El instalador se niega a sobrescribir una instalación existente. No use este procedimiento como actualizador de una máquina ya instalada ni elimine sus carpetas para forzarlo.

## Token y panel

Consultar **solo localmente**, sin pegar la salida en chats:

```bash
sudo cat /etc/telemediation-convergent/runtime.env
```

El valor `TMC_API_TOKEN` abre el panel. Por defecto use un túnel SSH; para acceso por IP aplique la guía de firewall. Abrir `http://192.168.1.202:8095`, introducir token, Connect. Enviar un grupo de registros: voz/SMS/datos deben llegar a `delivered`. Delivered significa publicados en la outbox local, no confirmados por un operador telefónico externo.

## Recolector

```bash
mkdir -p ~/tmc-collector-install
tar -xzf ~/tmc-collector-0.1.0.tar.gz -C ~/tmc-collector-install
cd ~/tmc-collector-install/telemediation-convergent
sudo bash scripts/install_collector.sh
sudo systemctl status tmc-collector --no-pager
sudo python3 scripts/check_collector.py
sudo journalctl -u tmc-collector -n 5 --no-pager
```

Agrega `/etc/tmc-collector/collector.env`, `/var/lib/tmc-collector/spool.sqlite3` y `tmc-collector.service`. No reinicia la aplicación. El ID de host por defecto del instalador es `tmc-lab-01`; si cambia, debe coincidir con `OPENOPS_HOST_ID` del receptor.

Al principio `destination_configured:false`, `sent:0`, `queued` crece cada 15 segundos. Eso demuestra recolección local; no entrega. El primer porcentaje de CPU del servicio puede ser null porque todavía falta un intervalo de medición.

Continúe con la [conexión entre máquinas](05-conexiones-credenciales.md) después de instalar B.
