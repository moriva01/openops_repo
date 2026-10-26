# Repository consolidation validation

Validated on October 26, 2026 from `hackaton/openops_repo`:

- 12 TeleMediation/collector tests passed using the consolidated source.
- Both tar.gz packages were generated and their SHA-256 matched the previous source version.
- The OpenOps image built from `apps/openops` without private files in its build context.
- 8 receiver/monitor tests passed in a container from that image, using temporary schemas in real PostgreSQL.
- Preparation scripts passed tests in a temporary directory with dummy credentials, custom address/host and preservation of existing secrets.
- Local Markdown links, Python syntax and private-file boundaries were checked with `tools/verify_repository.py`.
- Git was initialized locally, without a commit, remote or publication.

Consolidation did not reinstall Linux, change firewall rules or migrate running containers/credentials. Tests do not replace a full clean Zetaris/Nightshift deployment; obtain those products separately.

Generated packages in `apps/telemediation-convergent/dist/` are local outputs ignored by Git. Their source and builders allow regeneration.
