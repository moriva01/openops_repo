# Pruebas de aceptación y diagnóstico

## Pruebas automatizadas

Desde `apps/telemediation-convergent`:

```text
python -m unittest discover -s tests -v
```

12 pruebas: tres canales, convergencia, duplicados/conflictos, rechazo, colas, pausas, recuperación, API autenticada, CPU/memoria, spool durable y confirmaciones parciales. El HTTP de la prueba usa un puerto local temporal y una base temporal. No depende de la app de la VM.

Desde `apps/openops`, con su entorno preparado y contenedores arriba:

```powershell
docker compose exec -T receiver python -m unittest discover -s tests -v
```

8 pruebas con PostgreSQL real: recepción/autenticación, deduplicación, rollback por conflicto, validación, condición sostenida, reconocimiento, recuperación distinta, stale/consulta fallida, huecos y deshabilitación. Los datos de prueba se aíslan en esquemas temporales; no se insertan como telemetría de producción.

## Aceptación de las dos máquinas

| Paso | Evidencia esperada |
|---|---|
| API Linux | `/health/live` responde alive |
| Procesos | Tres `tmc-*` activos; heartbeat reciente |
| Tráfico | Tres tipos de registro llegan a delivered |
| Recolección | Diagnóstico muestra host real, app reachable, sin errores |
| Envío | `destination_configured:true`, `sent>0`, cola se vacía |
| Persistencia | `receiver_status.py` muestra muestras y última observación reciente |
| Zetaris | `latest()` devuelve ID de muestra real |
| Portal | CPU/memoria/cola visibles y `Zetaris · ok` |
| Falla | VOICE bloqueado: pending y alerta tras duración |
| Reconocimiento | Sigue activa, con acknowledged_at |
| Recuperación | Dos observaciones sanas, alerta resolved, evidencia e historial |

La prueba real del laboratorio se registra en `apps/openops/VALIDATION.md`. Los nuevos despliegues deben ejecutar su propia aceptación; no heredan automáticamente ese resultado.

## Comandos Linux

```bash
sudo systemctl status tmc-api tmc-mediation tmc-delivery tmc-collector --no-pager
sudo journalctl -u tmc-collector -n 20 --no-pager
sudo journalctl -u tmc-mediation -n 20 --no-pager
ss -lnt | grep 8095
curl http://127.0.0.1:8095/health/live
curl http://192.168.1.17:8096/health/ready
```

El último comando prueba conectividad, no autenticación de ingesta ni almacenamiento. `check_collector.py` se ejecuta con sudo desde el paquete extraído. No imprime claves.

## Comandos Windows

```powershell
docker compose ps
docker compose logs --tail 30 receiver
python scripts/receiver_status.py
Invoke-RestMethod http://192.168.1.17:8096/health/ready
docker inspect zetaris-driver-1 --format '{{json .NetworkSettings.Networks}}'
```

No publicar `docker inspect` completo: incluye variables de entorno. Las consultas de arriba filtran red o estados. Evitar `docker compose config` completo en reportes porque puede interpolar secretos.

## Fallas habituales

| Síntoma | Revisar |
|---|---|
| Docker cliente responde, motor no | Abrir Docker Desktop, terminar primera configuración/WSL, reinicio si lo exige |
| Pull Zetaris authentication required | Login del registro de su cuenta, sin copiar credenciales al chat |
| Bootstrap proveedor aún running | Esperar carga inicial; no confundir tarea en curso con servicio caído |
| Panel :8095 inaccesible | TMC_BIND, servicio API, firewall de A, IP puente, o túnel |
| API 401 | Token correcto del aplicativo y encabezado Bearer |
| Operación OpenOps 403 | Se necesita token operador, no lectura o ingesta |
| Collector sent 0, destino false | Falta destination.env/drop-in; es cola local esperada |
| Collector error y cola crece | Firewall Windows, ruta/IP, receptor, token de ingesta, estado DB |
| Ingesta 400 | Relojes, host ID, JSON/esquema; no eliminar spool para ocultarlo |
| Ingesta 409 | UUID reutilizado con contenido diferente; revisar productor y conservar evidencia |
| Ingesta 503 | PostgreSQL no disponible; datos deben quedar en spool |
| Zetaris no resuelve DB | Driver unido a `openops_default`, nombre `openops-db-1`, fuente configurada |
| Zetaris login falla | Login actual en `.local/zetaris.env`, no contraseña antigua del primer arranque |
| No-data en monitor | Última muestra de menos de 60 s, aplicación accesible, consulta Zetaris y campo disponible |
| Alerta no abre en el primer minuto | Duración y muestras nuevas; varias consultas del mismo evento no suman |
| Alertas siguen tras deshabilitar | Comportamiento diseñado: deshabilitar no significa recuperar |
| Nightshift catálogo pero no genera | Configurar proveedor/lane y ejecutar texto real; salud sola no basta |

Para reportar, incluya estados, tipo de error y tiempos; nunca `.env`, tokens, passwords o cuerpos con credenciales.
