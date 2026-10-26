# Instalar máquina B: centro Windows

## Prerrequisitos

Instale Docker Desktop, habilite backend WSL2 y arranque Docker. Instale Git y Python para los scripts de preparación. Si Windows presenta el alias Microsoft Store al ejecutar `python`, use su intérprete instalado (`py` o ruta completa).

```powershell
docker version
docker compose version
wsl --status
docker info --format '{{.NCPU}} CPUs / {{.MemTotal}} bytes'
```

Debe responder el servidor Docker, no solo su cliente. No hace falta instalar Ubuntu para que Docker use su distribución interna WSL2. Los scripts bash del proveedor sí requieren un entorno bash compatible; en el laboratorio se usó Git Bash para preflight/verify y Compose desde Windows. Para otra instalación siga el método Windows/WSL recomendado por el proveedor.

## Zetaris: producto externo

1. Cree su cuenta en https://cloud.enterprise.zetaris.com/register .
2. En Run locally descargue `zetaris-platform.zip` desde https://cloud.enterprise.zetaris.com/dashboard/download .
3. Extraiga fuera del repositorio, por ejemplo `C:\OpenOps\zetaris-platform`.
4. Ejecute localmente el comando de login al registro entregado por su cuenta. No pegue ese comando en chats ni commits.
5. Revise la configuración privada `.env` del proveedor y configure el administrador **antes del primer arranque**. Conserve los demás parámetros suministrados. No use el archivo para servidor público en un portátil sin revisar sus requisitos.
6. Desde la carpeta del proveedor, ejecute `preflight.sh` con bash, luego:

```powershell
docker compose pull
docker compose up -d
```

7. Ejecute `verify.sh` con bash. `init` y `bootstrap` deben terminar con exit 0; los demás servicios deben estar saludables. La primera descarga y la carga de datasets pueden tardar varios minutos.

Abrir http://localhost:3000 . No se redistribuye aquí el bundle, su `.env`, sus credenciales ni su driver. Referencia oficial: https://github.com/zetaris/getting-started . Los nombres de contenedor documentados corresponden al bundle validado; si el proveedor cambia nombres/puertos, adapte nuestros scripts explícitamente.

## OpenOps: instalación nueva

Desde `apps/openops` del checkout:

```powershell
python scripts/prepare_receiver.py --platform-env "C:\OpenOps\zetaris-platform\.env" --bind-ip 192.168.1.17 --host-id tmc-lab-01
docker compose up -d --build
```

El preparador no depende de la antigua ubicación del proyecto. Genera claves aleatorias en `.env` y `.local`, preservando archivos existentes. Alternativa: cree `.local/zetaris.env` a partir de `zetaris.env.example`, con su login actual, y ejecute el preparador sin `--platform-env`.

Si cambió la contraseña en el UI de Zetaris después del primer arranque, el `.env` del proveedor puede no reflejarla: actualice privadamente `.local/zetaris.env`. No imprima su contenido.

Adjunte el driver a la red de datos privada:

```powershell
docker network connect openops_default zetaris-driver-1
```

Si ya está adjunto, no necesita repetirlo. `scripts/start_monitoring.ps1` inicia el stack y comprueba esa conexión; tras recrear el driver de Zetaris debe restaurarla. No hace falta publicar PostgreSQL a la LAN.

Registre la fuente y compruebe consultas:

```powershell
docker compose exec -T receiver python -m receiver.setup_data
docker compose ps
Invoke-RestMethod http://192.168.1.17:8096/health/ready
```

`setup_data` crea la vista y el usuario de lectura en **nuestra** base, valida SELECT 1/descubrimiento en Zetaris y registra `openops_pg.monitor_samples`. El registro contiene una conexión JDBC al PostgreSQL propio; no escribe telemetría en el metastore de Zetaris. Sin muestras todavía, la consulta de datos puede devolver lista vacía; el monitor indica no-data, no una falla de la aplicación.

Ejecute la regla de firewall de la guía de infraestructura y conecte el recolector mediante SCP. Luego:

```powershell
python scripts/receiver_status.py
python scripts/prepare_portal.py
```

El acceso de operador queda en `.local/portal-access.txt`. Abrir http://192.168.1.17:8096 e introducir el token en Connect. No es el token de TeleMediation ni el de ingesta.

## Nightshift y NVIDIA: preparación separada

Obtenga Nightshift Windows en https://meterless.ai/ y complete su verificación. Abra Setup -> Providers -> NVIDIA y configure allí su clave del proveedor. Seleccione un modelo disponible en Night/Lanes. Console proporciona base URL y token del Runtime, distintos de la clave NVIDIA.

Diagnóstico local sin mostrar secretos:

```powershell
& "$env:LOCALAPPDATA\Nightshift\cli\ns.cmd" status --json
& "$env:LOCALAPPDATA\Nightshift\cli\ns.cmd" discover --json
```

Un runtime sano o una lista de modelos no prueban generación: se necesita una solicitud real y comprobar el modelo en su recibo. Esa prueba se hizo en el laboratorio, pero OpenOps todavía no llama a Nightshift y no implementa World Model. No agregue claves NVIDIA a `.env` de OpenOps ni a la VM.
