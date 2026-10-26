# Conexiones, autenticación y consultas

## Inventario de credenciales

| Credencial | Ubicación privada | Quién la usa | Qué permite |
|---|---|---|---|
| `TMC_API_TOKEN` | A: `/etc/telemediation-convergent/runtime.env` | Panel y recolector local | Leer/controlar app de laboratorio |
| `COLLECTOR_INGEST_TOKEN` / `OPENOPS_INGEST_TOKEN` | A: `destination.env`; B: `.env` | Recolector -> receptor | Enviar muestras del único host registrado |
| `OPENOPS_READ_TOKEN` | B: `.env` | Consultas de lectura | Hosts/eventos/dashboard |
| `OPENOPS_ADMIN_TOKEN` | B: `.env`; nota local privada | Operador del portal | Lectura, configurar monitor, reconocer alerta |
| `OPENOPS_DB_PASSWORD` | B: `.env` | Contenedores OpenOps | Base propia; no enviar a A |
| `OPENOPS_ZETARIS_DB_PASSWORD` | B: `.env` y registro cifrado del proveedor | Zetaris -> PostgreSQL | SELECT de vista `monitor_samples` |
| Login Zetaris | B: `.local/zetaris.env` | Adaptador UI proxy | Consultas SQL con la cuenta configurada |
| Login del registro de imágenes | Almacén Docker privado | Docker pull | Descargar imágenes Zetaris |
| Token Nightshift Runtime | Console/runtime privado | Pruebas IA; integración futura | Acceder al runtime local |
| Clave NVIDIA | Providers en Nightshift | Nightshift -> NVIDIA | Modelo alojado, sujeto a condiciones del proveedor |

No hay claves reales en el repositorio. No son intercambiables. La VM nunca necesita la clave del modelo, la contraseña PostgreSQL ni el login de Zetaris.

Para consultar el token de TeleMediation, use localmente `sudo cat /etc/telemediation-convergent/runtime.env` y copie solo su valor al navegador. Para OpenOps, `python scripts/prepare_portal.py` genera la nota de acceso local sin imprimir el secreto. Nunca incluir esas salidas en logs, capturas compartidas o incidencias.

## Conectar A con B

Después de preparar B, desde Windows:

```powershell
$app = "C:\OpenOps\openops_repo\apps\openops"
scp "$app\.local\collector-destination.env" "$app\scripts\connect_collector.sh" labadmin@192.168.1.202:~/
```

En A:

```bash
sudo bash ~/connect_collector.sh ~/collector-destination.env
sudo journalctl -u tmc-collector -n 5 --no-pager
```

Este script valida actualmente el destino del laboratorio `192.168.1.17:8096/api/ingest`. Para otras direcciones debe actualizar conscientemente esa validación antes de ejecutarlo, además de `OPENOPS_BIND_IP` y firewall. No lo considere un instalador genérico de destinos arbitrarios.

Instala archivo root-only `/etc/tmc-collector/destination.env`, drop-in `/etc/systemd/system/tmc-collector.service.d/destination.conf`, recarga systemd y reinicia solo el recolector. Los archivos base y el token de la aplicación permanecen independientes.

Resultado esperado: `destination_configured:true`, `sent` mayor que cero y la cola bajando. Con una muestra por ciclo, `sent:1` y `queued:0` son normales. Con una cola grande se drena en lotes de 50 por ciclo. Consultar en B `python scripts/receiver_status.py` confirma almacenamiento.

## Protocolo del recolector

POST autenticado con Bearer, límite de 50 eventos/2 MiB en receptor. El recolector espera hasta cinco segundos; el receptor puede completar un commit aunque se pierda la respuesta. El reenvío conserva IDs y la base deduplica.

```json
{"schema":"openops.batch.v1","events":[{"schema":"openops.telemetry.v1","event_id":"UUID","host_id":"tmc-lab-01","hostname":"telemediation-01","observed_at":"fecha UTC","host":{},"application":{},"systemd_units":{},"collection_errors":[]}]}
```

Respuesta solo después de commit: `{"accepted_event_ids":["UUID"],"inserted":1,"duplicates":0}`. Las fechas se ilustran como texto; usar ISO-8601 real. El receptor valida el host con su credencial y rechaza fechas más de cinco minutos futuras. Compare relojes de ambas máquinas si aparecen errores 400.

## Zetaris

Fuente `openops_pg`, URL interna `jdbc:postgresql://openops-db-1:5432/openops`, driver `org.postgresql.Driver`, usuario limitado `openops_zetaris`. Solo comparte red el driver; no se publica la base.

Vista: ID de evento/host, epoch observado, CPU/memoria/disco, accesibilidad de app, antigüedad de pendientes, throughput, rechazos totales y pendientes/habilitación de VOICE. El payload original conserva más telemetría, pero la primera vista no expone todavía todas las métricas de SMS/datos/servicios.

Consulta de evaluación:

```sql
SELECT * FROM openops_pg.monitor_samples ORDER BY observed_epoch DESC LIMIT 1
```

El adaptador llama a `/api/auth/login` y `/api/proxy/sql-editor/sqls/run-query` en el UI de Zetaris, con ID de organización y UUID de petición. Convierte filas/encabezados del resultado; las cifras pueden llegar como strings o notación exponencial. No es la ruta REST directa `8888/api/v1.0` ni JDBC cliente `10000`.

La cuenta usada en este prototipo es la del administrador del lab. Una instalación de producción necesita cuenta/permisos reducidos y gestión de credenciales más completa. El script no crea tokens API del proveedor.

## Consultas de diagnóstico sin imprimir claves

```powershell
docker compose exec -T db psql -U openops -d openops -c "SELECT host_id,count(*),max(observed_at) FROM telemetry_events GROUP BY host_id;"
docker compose exec -T db psql -U openops -d openops -c "SELECT name,state,source_status,last_value FROM monitors;"
docker compose exec -T db psql -U openops -d openops -c "SELECT id,state,opened_at,acknowledged_at,resolved_at FROM alerts ORDER BY id DESC LIMIT 10;"
docker compose exec -T receiver python -c "from receiver.zetaris import latest; r=latest(); print({k:r.get(k) for k in ('host_id','event_id','voice_pending')} if r else 'No samples')"
```
