# Estado implementado

## Máquina A: monitoreada

Rocky Linux 9.8, Python 3.9.25, systemd. TeleMediation Convergent con API, mediación y entrega como servicios separados; SQLite como estado de aplicación. Voz/SMS/datos son registros de uso sintéticos, no tráfico telefónico real. Convergencia significa formato de uso común y agrupación por referencia de suscriptor; no suma segundos con bytes.

Recolector propio cada 15 segundos: CPU, memoria, disco raíz, uptime, carga, estado systemd de tres servicios y telemetría de la aplicación. Spool SQLite de máximo 1440 muestras; si se llena descarta las más antiguas y registra `retention_dropped`. La retención es limitada, no una garantía de cero pérdidas.

## Máquina B: monitoreo

Windows con Docker Desktop/WSL2. PostgreSQL propio, receptor autenticado, portal y evaluador. Zetaris consulta una vista de solo lectura de esta base. El evaluador usa Zetaris; las gráficas usan PostgreSQL directamente. No hay fallback silencioso a PostgreSQL si falla Zetaris.

Monitor inicial: pendientes de salida VOICE > 0 durante 60 segundos; recuperación con dos muestras distintas sanas. Se puede editar nombre, métrica, umbral, duración, recuperación y habilitación. El API admite severidad; el formulario actual conserva la existente. No hay pantalla de creación de varios monitores todavía.

Probado en dos máquinas: alerta abierta, reconocida sin resolver y resuelta al recuperar la salida. Ver `apps/openops/VALIDATION.md`. Las capturas y claves del entorno privado no forman parte del repositorio.

## IA y pendientes

Nightshift 1.2.7 respondió en una prueba separada con NVIDIA `nvidia/nemotron-3.5-bolt-e4b`. Eso confirma conectividad del proveedor, no integración de IA en OpenOps.

Pendientes: implementar World Model Engine de Meterless, investigación y evaluación con Nightshift, correlación de incidentes, webhooks/correo/SMS, escalamiento, varios hosts, RBAC, autenticación por usuarios, TLS y endurecimiento de producción. No se ejecuta reparación automática sobre servicios.

