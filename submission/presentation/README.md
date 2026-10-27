# OpenOps Evidence presentation

English review draft for the Open Agent Hackathon 2026.

## Files

- `OpenOps-Evidence-Hackathon.pptx`: editable 12-slide presentation with speaker notes and source references.
- `slides.md`: readable slide copy, speaker notes and supporting repository references.
- `assets/overview.png`: actual running portal screenshot after the reinstall and recovery tests.
- `assets/investigation.png`: actual completed investigation excerpt with observation citations.

## Review scope

The presentation covers intended users, the operational problem, the VOICE incident workflow, the two-machine deployment, actual sponsor contributions, bounded investigation roles, product screenshots, validation evidence, differentiation, proposed pilot priorities and reproduction instructions.

The portal account identity and host address/client metadata are hidden in the overview screenshot. Screenshots contain no API keys, passwords or signed connector URLs. The report's confidence wording is model output, not measured accuracy or proof of causality.

Live-install results refer to the participant's fresh installation and end-to-end tests on 26 October 2026, together with inspected receiver and provider logs. The offline examples use openly scripted generation and do not call live sponsor services. The deck distinguishes those evidence sources.

The current deployment has one registered telemetry view through Zetaris and one demonstrated monitored host. Portal charts read PostgreSQL directly. The World Model is a minimal adaptation of the Meterless reference architecture. Reports support human review and do not execute repairs.

The restart test required restarting the receiver after Zetaris became ready. The exact cause remains unconfirmed. See [restart procedure](../../docs/08-operations-and-migration.md#windows-restart-order).

Open the PowerPoint speaker notes for narration and implementation references. Edit `slides.md` alongside slide changes to keep the readable copy aligned. Review this draft before publishing or attaching it to the submission.
