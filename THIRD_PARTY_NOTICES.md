# Provenance and third-party notices

- TeleMediation Convergent is original code, licensed under MIT in `apps/telemediation-convergent/LICENSE`.
- OpenOps modules in this repository are original code; their MIT license is in `apps/openops/LICENSE`.
- Python and its standard library retain their Python/PSF licenses. The interpreter is not redistributed here.
- PostgreSQL retains the PostgreSQL license and is obtained as the external `postgres:16-alpine` image.
- Psycopg and its binary distribution retain their upstream licenses and notices. They are installed at image build time from `requirements.txt`.
- The Python base image, Docker Desktop, Zetaris and Meterless/Nightshift retain independent terms. MIT client code grants no rights to those products and does not guarantee free service usage.
- The Zetaris adapter uses documented interfaces; it does not incorporate the Zetaris engine or its libraries.
- Telecom records are synthetic and use an original schema.

References: https://www.postgresql.org/about/licence/ · https://www.psycopg.org/ · https://github.com/zetaris/getting-started · https://meterless.ai/
