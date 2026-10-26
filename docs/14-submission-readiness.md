# Submission readiness review

Reviewed on **26 October 2026**. Source baseline: `77f9026b00e493df04b39c7b8ca24afe851f4824`. This is an evidence review, not an organizer eligibility decision or a completed submission.

## Outcome

The running product demonstrates the core sponsor integrations and an operational incident circuit. The submission package is **not ready yet**: a final video, slide deck and completed HackOS entry were not found. Reproducibility still needs an isolated full live-install check. The follow-up now supplies three synthetic examples and an explicit offline judging path; see the completed items below.

## Source precedence

- **A — Public Official Rules:** [event page, rules section](https://hackathon.genai.works/event/open-agent-hackathon-2026#rules), reviewed including the initially collapsed sections from the page's serialized content.
- **B — Provided Technical Execution Guide:** `technical-execution-requirements.md`. Its opening explicitly says the Official Rules prevail and its guidance is recommended unless incorporated by the Rules.
- **C — Provided Meterless README and World Model architecture:** these define the minimal service contract and explain that the engines are reference architectures rather than mandatory installable packages.
- **D — Provided Participant Setup Guide PDF:** 30-page guide, dated 21 October; an onboarding/setup document, not the current submission checklist.
- **E — Repository, tests, live database and recorded validations:** evidence of implemented behavior, independent of claims in planning documents.

The Academy summary and older setup PDF describe Cursor as mandatory. A section 5 of the public rules makes it optional. Apply the current rules and describe the coding tools actually used. Do not claim Cursor usage without evidence. The final authenticated HackOS form and its latest resource documents have not been independently checked; compare them before submitting.

## Formal requirements versus evidence

| Requirement from A | Status | Evidence or remaining action |
|---|---|---|
| Zetaris and Meterless integration | Demonstrated | Registered read-only datasource; real evidence queries; persistent World Model services; Nightshift receipts. See [investigation](10-ai-investigation.md). |
| NVIDIA contribution | Demonstrated | Actual NVIDIA Nemotron generation recorded in successful investigations. |
| Repository with source, setup, usage and dependencies | Present | [Public repository](https://github.com/moriva01/openops_repo), application READMEs, installers and dependency files. GitHub API reports public visibility; local and remote HEAD matched at review. |
| Demo video, 1–4 minutes | Missing | Record the main incident workflow and show sponsor contributions. No final video was found in the checkout. |
| Slide deck | Missing | Cover users/problem, solution, architecture, stack, sponsor contribution, differentiation, screenshots and roadmap. No final deck was found. |
| Sponsor explanation | Partial | Technical evidence is documented; consolidate a short submission-ready narrative and align the deck/video. |
| One selected challenge category | Unverified | Proposed: **The Agent That Can Explain Why**. The team's current form selection was not inspected. |
| Solo/team registration and participant eligibility | Partly known | Builder confirmed a solo team; account-level eligibility and final entry remain unverified. |
| New-work provenance; declare earlier components | Needs final declaration | Visible source commits are dated within the event. Dates alone do not establish provenance; list actual earlier components/dependencies accurately. |

Submission closes **27 October 2026, 23:45 UTC / 18:45 America/Bogota**. No entry was submitted or modified during this review.

## Technical guide recommendations

These are readiness and judging improvements from B, not additional disqualification rules inferred by this review.

| Area | Status | Finding |
|---|---|---|
| Programmatic operation | Present | Authenticated JSON endpoints enqueue/read investigations; the background worker runs independently of the browser. Add a short judge-facing invocation example. |
| Reproducible container build | Present, clean deployment unproven | Dockerfile installs dependencies at build time; Compose preserves state. Earlier builds/tests passed, but a full fresh deployment with provider setup has not been verified. |
| No local GPU | Present | Models run through Nightshift's hosted NVIDIA route. |
| Bounded runs | Present | 200-second attempt budget, at most five generation calls, three evidence queries and one revision. Provider calls have timeouts; failed attempts stay explicit. |
| Offline sample mode | Implemented in follow-up | Root `run.py`, explicit `--sample` or `SAMPLE_MODE=true`, SQLite, scripted generation and no live provider imports. Validated with Docker network disabled. |
| Three example inputs and matching outputs | Implemented in follow-up | `input_examples/`, `output_examples/` and synthetic JSONL traces reproduce exactly. They are fixtures, not three live model-quality evaluations. |
| Inspectable traces | Partial | Per-run JSONL, database trace, reports, manifests and model receipts exist in private runtime storage. Synthetic per-run evidence is now published with examples. A sanitized live-run export remains separate follow-up work. |
| Meterless minimum | Demonstrated subset | `WorldStoreService`, `IngestPipelineService`, `ContextBuilderService`; stable IDs, atomic/idempotent ingest and context consumption have tests. Advanced features are explicitly absent. |
| Secrets | Good current boundary | Runtime files are ignored; signed connector URLs are encrypted and omitted from API responses. Earlier publication audits passed. Repeat before the final release and inspect demo visuals. |
| Data documentation | Present | Synthetic telecom usage and real host metrics are distinguished. PostgreSQL view and Zetaris registration are documented. |
| Single-command judging path | Partial | Setup spans the Linux node, PostgreSQL, Zetaris, Nightshift, credentials and network attachment. Root-level directions need a concise first-run route. |

## Evidence already available

- **41 automated tests** passed in the latest recorded test run. Review did not repeat unchanged tests merely to inflate counts.
- Real VOICE blockage and healthy recovery traversed application → collector → PostgreSQL → Zetaris → monitor → durable notification delivery. Acknowledgement did not clear the incident. See [circuit evidence](12-webhook-circuit-demo.md).
- Real Teams delivery was accepted with HTTP 202, and the participant confirmed receipt. See [Teams validation](13-outgoing-webhooks-and-teams.md).
- At review, Zetaris status was healthy, four investigations had completed, and the newest completed analysis retained a supported evaluator verdict with three model receipts.
- Repository visibility was public. The remote HEAD matched the local baseline above. New review files still require the normal commit/publish process before they appear online.

## Competition positioning

Recommended primary category: **The Agent That Can Explain Why**, subject to the participant's final choice. Lead with the difference between a healthy process and a disabled output: monitoring establishes a symptom, while the investigation examines application configuration and other evidence before proposing an explanation.

The current agent queries **one registered PostgreSQL view through Zetaris**. Host, service and application signals are distinct evidence groups, but this is not demonstrated federation across independent registered systems. Do not describe it as a broad multi-source integration. Category fit and sponsor differentiation would be stronger with clear evidence of how those groups are compared; adding another independent source is optional scope, not a proven requirement of the current implementation.

The product's commercial hypothesis is reduced investigation effort for small operations teams. No measured time savings, production deployment, paying customers, accuracy percentage or guaranteed root-cause correctness has been established. Avoid those claims.

The World Model is a minimal reference-architecture implementation. Do not describe it as a complete vendor engine. The investigator, evaluator and planner are separate bounded generation roles using shared grounded state. Tool choices also include an explicit required-evidence policy; do not attribute every choice solely to model autonomy.

## Ordered completion plan

1. **Completed: prepare a judge-facing synthetic evidence package:** three neutral input/output scenarios with expected behavior, source/license notes and sanitized traces. Suggested cases: blocked VOICE with healthy processes; resource contention or a distractor; insufficient evidence with explicit abstention. Clearly distinguish fixtures from live captures.
2. **Completed: add a labeled offline demonstration path:** no live Zetaris/Nightshift calls or external notifications. Any recorded replay must identify itself as replay, never as fresh model generation or live sponsor integration.
3. **Validate from a clean checkout in isolation:** new private credentials, separate state and ports, documented provider prerequisites, expected startup/API output. Preserve the current working lab. Include the monitored-node package and Windows configuration, not only an image build.
4. **Record a roughly three-minute demonstration:** problem/user; controlled fault; sustained alert; evidence-backed investigation and critique; outbound Teams alert; restored output and recovery notification. Hide credentials and private identity. Use actual timings rather than fabricating speed.
5. **Create the required deck and final narrative:** problem/users, workflow, architecture, actual sponsor use, differentiation, product visuals, limitations and next steps.
6. **Finish the authenticated entry:** category, links, earlier-component declaration and sponsor explanation. Open every uploaded link independently before final submission.

The public scoring weights are Impact 30, Technical 20, Innovation 15, Demo 15, Product & UX 10 and Sponsor technology 10. Prioritize problem clarity, visible evidence and a reproducible demonstration over additional administration features.

## Ready-to-adapt sponsor explanation

Zetaris supplies the agent's incident observations through a registered, read-only telemetry view. The investigation does not silently switch to direct PostgreSQL if Zetaris fails. Portal charts read PostgreSQL separately; this is disclosed.

The Meterless World Model adaptation persists typed entities, immutable observations, provenance and incident contexts. Planner, investigator and evaluator consume bounded context built from that state. Tests cover idempotency, rollback/resumption and context isolation.

Meterless Nightshift is the investigation's configured generation provider. Its injected adapter runs bounded planning, investigation and critique. Successful traces retain routed model identities and provider receipts. NVIDIA Nemotron contributes actual generation through that route. Citation checks and critique support operator review; the platform does not execute repairs or prove causality.

Cursor is optional under the reviewed public rules. Disclose actual development tools and actual earlier components without inventing a development history.

## Offline follow-up completed

[Offline examples](15-offline-examples.md) now provide three standard-library-only cases with paired results and traces. Shared live monitoring and investigation logic runs with SQLite-backed World Model services and an openly scripted generator. Ten offline tests passed; 41 live-backend regression tests passed in isolated PostgreSQL schemas. All three examples also ran with Docker networking disabled, a read-only root filesystem and temporary output storage. Production services and notification configuration were not changed. Full live installation from a clean machine, video, slides and final submission remain pending.
