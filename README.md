# OpenOps — repositorio del laboratorio de operaciones

Código original de **TeleMediation Convergent**, su recolector Linux y **OpenOps**, la plataforma de monitoreo. Documentación del estado implementado al 26 de octubre de 2026. Las interfaces de los aplicativos están en inglés.

Dos máquinas independientes: una ejecuta la aplicación de telecomunicaciones sintética; otra recibe su telemetría, la almacena, la consulta mediante Zetaris y evalúa monitores. Una VM es una forma de desplegar la primera máquina, no un requisito de la arquitectura.

## Comenzar

1. [Estado actual y límites](docs/00-estado.md).
2. [Arquitectura completa](docs/01-arquitectura.md).
3. [Requisitos, puertos y firewall](docs/02-infraestructura.md).
4. [Instalar la máquina monitoreada](docs/03-instalacion-monitoreada.md).
5. [Instalar el centro de monitoreo Windows](docs/04-instalacion-centro.md).
6. [Conectar las dos máquinas y Zetaris](docs/05-conexiones-credenciales.md).
7. [Manual de uso](docs/06-uso.md).
8. [Pruebas y diagnóstico](docs/07-pruebas-diagnostico.md).
9. [Operación, respaldo y migración de la instalación existente](docs/08-operacion-migracion.md).
10. [Validación del repositorio consolidado](docs/09-validacion-repositorio.md).

## Contenido

```text
apps/
  telemediation-convergent/  Aplicación, recolector, instaladores y empaquetadores
  openops/                  Receptor, PostgreSQL Compose, monitor, portal, adaptador Zetaris
docs/                       Guías de las dos máquinas
```

Cada aplicativo conserva su README técnico, pruebas y scripts. Los archivos de planificación dentro de `apps/openops` son antecedentes; ante diferencias, prevalecen `docs/00-estado.md` y el código actual. `apps/openops/VALIDATION.md` registra la prueba real de alerta.

## Qué funciona

Telemetría real de servidor, portal de mediación sintética con voz/SMS/datos, spool durable, receptor autenticado, PostgreSQL propio, fuente de solo lectura en Zetaris, monitor configurable, gráficas y ciclo de alerta con reconocimiento y recuperación automática.

**No hay todavía investigación de incidentes con IA, correlación, notificaciones o remediación automática.** Nightshift/NVIDIA fue instalado y probado separadamente en el laboratorio; no está conectado al código de OpenOps. No confundir una alerta resuelta con una reparación ejecutada por el sistema.

## Qué no se incluye


Esta consolidación del código no cambia las rutas de los servicios que ya están ejecutándose. Consulte la guía de migración antes de operar el despliegue actual desde esta carpeta.
