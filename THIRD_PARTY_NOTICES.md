# Procedencia y licencias

- TeleMediation Convergent es código original, con licencia MIT en `apps/telemediation-convergent/LICENSE`.
- Los módulos de OpenOps de este repositorio son código original; licencia MIT en `apps/openops/LICENSE`.
- Python y su biblioteca estándar: licencias Python/PSF; no se redistribuye el intérprete aquí.
- PostgreSQL: licencia PostgreSQL; se obtiene como imagen externa `postgres:16-alpine`.
- Psycopg y su distribución binaria: conservar sus licencias y avisos upstream; se instalan al construir la imagen desde `requirements.txt`.
- La imagen Python base, Docker Desktop, Zetaris y Meterless/Nightshift conservan sus términos independientes. El código MIT del cliente no otorga derechos sobre esos productos ni garantiza costo cero de servicios.
- El adaptador Zetaris sigue interfaces documentadas; no incorpora su motor ni sus librerías.

Referencias: https://www.postgresql.org/about/licence/ · https://www.psycopg.org/ · https://github.com/zetaris/getting-started · https://meterless.ai/
