# Operación, respaldo y migración

## Código consolidado vs instalación actual

Esta carpeta es la fuente consolidada para próximos cambios. Copiar código no mueve contenedores, bases ni archivos privados. El laboratorio original está ejecutando imágenes construidas desde la carpeta anterior `openops-evidence`; los servicios Linux usan `/opt/telemediation-convergent`.

Los dos checkouts de OpenOps declaran el mismo proyecto Compose `openops`, mismos contenedores y mismos volúmenes. No pueden arrancarse como despliegues independientes en el mismo puerto. Nunca genere nuevas contraseñas y las aplique a un volumen existente: no cambian automáticamente la contraseña ya almacenada en PostgreSQL.

## Migrar el centro existente al nuevo checkout

Este procedimiento se documenta para una ventana de mantenimiento; no se ejecuta automáticamente durante la consolidación.

1. Verifique servicios, volúmenes y credenciales existentes. Respalde base, logs y configuración privada.
2. Copie **privadamente**, fuera de Git, el `.env` original a `apps/openops/.env` y la carpeta `.local` necesaria a `apps/openops/.local`. Mantenga las claves existentes. Las capturas y pruebas visuales viejas son opcionales; no forman parte del código.
3. Compare variables sin imprimir valores. `OPENOPS_HOST_ID` puede no existir en el archivo anterior: Compose conserva por defecto `tmc-lab-01`. Revise `.local/zetaris.env` y direcciones.
4. Desde `apps/openops`, ejecute `docker compose up -d --build`. El proyecto `openops` reutiliza sus volúmenes y recrea el receptor desde la fuente nueva; puede haber una interrupción breve y el spool debe retener muestras.
5. Si hace falta restaure red con `scripts/start_monitoring.ps1`. No debe regenerar la fuente ni su password solo por mover el checkout.
6. Compruebe salud, recepción, consulta Zetaris y monitor. Desde ese momento use solo el nuevo checkout para operar Compose.

No se ejecuta `down -v`, ni se borran bases o archivos para solucionar una migración. La app Linux no necesita reinstalarse para mover el repositorio Windows.

## Respaldos

### Linux

Para una copia consistente simple, detener temporalmente los tres servicios de aplicación y el recolector, respaldar como root sus directorios `/var/lib/telemediation-convergent`, `/var/lib/tmc-collector`, `/etc/telemediation-convergent` y `/etc/tmc-collector`, y volver a iniciar los servicios. La configuración contiene secretos: cifrar/controlar el destino y no enviarla a Git. Otra opción es usar el API de backup SQLite con escritores activos; copiar solo el `.sqlite3` mientras usa WAL puede omitir datos.

Conservar también los units `tmc-*` y el drop-in del recolector, o reconstruirlos con los instaladores apropiados en una máquina nueva. Los instaladores actuales rechazan sobreescritura; no son migraciones de versiones.

### PostgreSQL OpenOps

Desde `apps/openops`, guarde el dump en un destino de respaldo privado. Use `docker compose exec -T db pg_dump -U openops -d openops` y una herramienta que preserve UTF-8/bytes al escribir; evite redirecciones de Windows PowerShell antiguo que puedan recodificar el SQL. Para archivos grandes use `pg_dump` a archivo dentro del contenedor y `docker cp` al almacenamiento privado.

El dump de una base no incluye contraseñas de roles globales. Conserve el `.env` original y recree de forma controlada el usuario de solo lectura. Respalde `openops-logs` si necesita conservar logs operativos. Los eventos, monitores, alertas e historial viven en la DB.

### Zetaris y Nightshift

Respalde con el procedimiento del proveedor sus volúmenes y configuración, especialmente el `.env` y material de cifrado de Zetaris; la contraseña de su keypair no es reemplazable por una credencial nueva. No guarde claves del modelo o tokens Runtime en este repositorio.

## Reinicios y continuidad

- Servicios Linux habilitados arrancan con systemd. Los contenedores usan restart unless-stopped; Docker Desktop debe estar ejecutándose.
- Si el receptor está parado, el recolector conserva hasta 1440 muestras. Al recuperar, los reenvíos se deduplican.
- Si la app está parada pero el recolector funciona, este puede reportar API inaccesible y estado systemd de los procesos.
- Si el recolector/máquina A cae, no hay muestras nuevas: el monitor indica no-data; no inventa recuperación.
- Monitores y alertas persisten. La continuidad del temporizador usa fechas de observación y límites de frescura.

## Rotación de credenciales

No hay flujo automatizado de rotación. Cambiar un secreto exige actualizar sus dos extremos y reiniciar/recrear el consumidor correspondiente, sin mostrarlo. La contraseña PostgreSQL del `.env` no rota una base existente; primero cambie el rol dentro de PostgreSQL de forma controlada. El password de la fuente Zetaris debe actualizarse también en el registro del proveedor. Una clave comprometida debe reemplazarse, no solo borrarse del archivo.

## Siguiente desarrollo

Investigación Meterless/World Model, evaluación de hipótesis, notificaciones y más monitores. Los cambios deben comenzar aquí, mantener pruebas y actualizar el estado implementado. No presentar capacidades pendientes como funciones disponibles.
