# Manual de uso

## TeleMediation Convergent

Abrir panel :8095 e introducir token de la aplicación. Los controles de Processing pausan la lógica, no matan el proceso; el heartbeat puede seguir vivo. Los controles Input/Output habilitan cada portal.

Send voice, SMS and data records genera un registro sintético por canal. El flujo es received -> mediated -> delivered. Datos inválidos van a rejected con motivo; repetir mismo ID/contenido es idempotente y cambiar su contenido devuelve conflicto.

Los portales de salida son APIs con cursor, no sockets telco. `GET /api/outputs/voice?after=0`, equivalentes SMS/data, devuelve hasta 100 registros y `next_cursor`. El consumidor debe persistir su cursor. La aplicación no registra confirmación de un sistema de billing externo.

`GET /api/convergence` agrupa por referencia de suscriptor y tipo/unidad. SHA-256 del identificador es pseudonimización estable; no significa anonimato. No use datos de abonados reales en este laboratorio.

## OpenOps

Abrir :8096, introducir token de lectura u operador y Connect. El navegador lo conserva solo en memoria de esa sesión. El token de ingesta no sirve para el portal.

### Overview

Último host observado, alertas activas, pendientes de VOICE, CPU y gráficas de CPU/memoria y backlog. Se muestran hasta 120 observaciones, ordenadas por fecha de medición. Una muestra antigua recibida ahora no indica salud actual. La insignia Zetaris indica estado de la última consulta, no diagnóstico de IA.

### Monitor configuration

Primer monitor editable: nombre, métrica de lista cerrada, mayor que umbral, duración en segundos, número de muestras sanas para recuperación y habilitación. Valores disponibles: pendientes de VOICE, CPU, memoria, disco. Save monitor requiere token de operador.

El motor evalúa cada 15 segundos; el periodo real puede alargarse ante una consulta lenta. Para abrir requiere continuidad de observaciones; una muestra repetida no suma otra evaluación. La recuperación exige muestras distintas. No hay alarma nueva cada 15 segundos: se actualiza el mismo ciclo.

Alerta activa impide redefinir condición/umbral/duración/recuperación para no borrar evidencia por cambios de configuración. Puede deshabilitarse el monitor, conservando la alerta abierta. Rehabilitarlo permite continuar evaluación con datos nuevos.

### Alerts y Activity

View evidence muestra fuente, evento, host, fecha observada, valor, umbral y revisión de configuración. Acknowledge marca atención del operador; no cierra ni modifica la aplicación. Tras recuperación, permanece una fila resuelta con evidencia de cierre. Activity conserva opened, acknowledged, resolved y cambios de configuración/no-data.

En no-data no hay prueba de salud: fallas de Zetaris, app inaccesible, valores faltantes o telemetría vencida no resuelven una alerta abierta. Actualmente no-data aparece como estado del monitor e historial, no como una alerta autónoma de disponibilidad.

## Demostración guiada

1. Confirmar servicios activos y portal VOICE habilitado.
2. En OpenOps conservar pendientes >0 por 60 segundos, recuperación 2.
3. En TeleMediation deshabilitar Output VOICE y generar registros.
4. SMS/datos continúan; voz queda mediated. El recolector manda estado y pendientes.
5. OpenOps pasa pending -> firing y crea una alerta. Reconocerla y revisar evidencia.
6. Reactivar Output VOICE. Esperar vaciado y dos muestras sanas (aproximadamente 30 segundos más la consulta).
7. Comprobar alerta resuelta, historial y monitor normal.

No hace falta parar servicios ni cambiar firewall para esta demostración. No deje el portal deshabilitado al terminar si quiere volver al estado base.

## Qué no hace el portal todavía

No investiga con un LLM, no propone causa raíz automáticamente, no envía correos/webhooks/SMS, no reinicia aplicaciones, no administra inventario completo ni crea monitores múltiples desde la pantalla. Estas funciones están en el diseño futuro, no en el producto actual.
