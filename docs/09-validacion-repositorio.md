# Validación de la consolidación

Validado el 26 de octubre de 2026 desde `hackaton/openops_repo`:

- 12 pruebas de TeleMediation/recolector pasaron desde los archivos copiados.
- Los dos paquetes tar.gz se generaron y sus SHA-256 coinciden con la versión anterior del código.
- La imagen OpenOps se construyó desde `apps/openops`, sin archivos privados en su contexto.
- 8 pruebas de receptor/monitor pasaron en un contenedor de esa imagen, usando esquemas temporales en PostgreSQL real.
- Los scripts de preparación se probaron en una carpeta temporal, con credenciales ficticias, IP/host personalizados y preservación de claves existentes.
- Revisión de enlaces Markdown locales, sintaxis Python y límites de archivos privados mediante `tools/verify_repository.py`.
- Se inicializó Git local, sin commit, remoto o publicación.

No se reinstaló Linux, no se modificó firewall y no se migraron contenedores ni credenciales del despliegue en ejecución durante esta consolidación. Las pruebas no sustituyen una instalación nueva completa de Zetaris/Nightshift; esos productos se obtienen fuera del repositorio.

Los paquetes generados en `apps/telemediation-convergent/dist/` se conservan como salida local y están ignorados por Git. La fuente y los empaquetadores permiten regenerarlos.
