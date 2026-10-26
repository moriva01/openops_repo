# Repository consolidation validation

Validated on October 26, 2026 from `hackaton/openops_repo`:

- 12 TeleMediation/collector tests passed using the consolidated source.
- Both tar.gz packages can be regenerated from source; they were rebuilt after documentation and deployment-identity updates.
- The OpenOps image built from `apps/openops` without private files in its build context.
- Initially 8 receiver/monitor tests passed. AI integration expanded this to 22 passing tests, using temporary schemas in real PostgreSQL.
- Preparation scripts passed tests in a temporary directory with dummy credentials, custom address/host and preservation of existing secrets.
- Local Markdown links, Python syntax and private-file boundaries were checked with `tools/verify_repository.py`.
- Source is versioned in Git. Private runtime settings and generated artifacts remain ignored.

Initial consolidation did not move runtime state. During AI integration, the receiver was rebuilt from this checkout with existing credentials and volumes preserved. Tests do not replace a full clean Zetaris/Nightshift deployment; obtain those products separately.

Generated packages in `apps/telemediation-convergent/dist/` are local outputs ignored by Git. Their source and builders allow regeneration.

Console expansion passed 33 tests covering roles, sessions, user-owned credentials, host scope, severity changes, tickets and notification contracts. Browser smoke checks covered all five sections, existing reports, admin forms and responsive layouts. Only admin exists in the production user table.
