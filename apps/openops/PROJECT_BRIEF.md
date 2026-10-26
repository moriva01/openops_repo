# OpenOps Evidence

Working proposal prepared 26 October 2026. Status: design and registration copy only; no working agent or validated sponsor integration yet.

## Product

An incident investigation agent for small IT operations teams. Given a service and incident time window, gather metrics, application logs and deployment events; compare possible explanations; return a report with source identifiers, timestamps, uncertainty and practical next checks.

Example question: Why did ingestion latency increase after a deployment?

## MVP demo

Use an original, reproducible synthetic incident: a worker deployment reduces processing throughput; a queue grows and latency rises while CPU remains normal. Include a second normal service as a negative control. Show that a coincident CPU warning on an unrelated service is not evidence for the affected service. Include an insufficient-evidence scenario so the agent can abstain.

The result is a supported hypothesis, not a proven causal diagnosis. A recommendation is not executed automatically.

## Intended sponsor contributions

- Zetaris: query and correlate metrics, logs and deployment records across sources; retain source IDs and time filters with the retrieved evidence. Prefer at least two genuinely distinct source connections supported by the participant environment. Do not describe a local join as a Zetaris query.
- Meterless Nightshift: primary AI provider, through an injected generator using its OpenAI-compatible endpoint. Generate and compare hypotheses over the evidence packet, cite known IDs and state missing information.
- Meterless World Model Engine: implement the reference architecture, starting with WorldStoreService, IngestPipelineService and ContextBuilderService. Ingest observations with provenance and idempotency; build the grounded context consumed by the investigator and evaluator. Full engine specification and conformance checks are pending receipt of WORLD_MODEL_Agent_Engine.md. Nightshift alone does not satisfy the engine requirement described by the supplied Technical Execution Guide.
- Optional NVIDIA: use only if accessible and valuable; document the exact technology and observed contribution. Do not claim it is present by default.

## Agent workflow

1. Validate the requested service and bounded time range.
2. Retrieve evidence through the configured Zetaris connector.
3. Decide which additional source to inspect based on gaps (deployments, metrics or logs); keep a bounded tool-call budget.
4. Pass only the synthetic evidence packet to Meterless for hypothesis evaluation.
5. Validate output: reject unknown citation IDs and malformed reports; distinguish observed facts from hypotheses.
6. Publish timeline, evidence, competing hypotheses, missing facts and next checks.
7. Export an execution trace with tool names, timings, source IDs, provider status and validation outcome. Never include tokens or credentials.

## Scope


## Public-source boundary

Write the submission in this standalone directory. Prior lab materials are context only. Do not copy vendor packages, internal parser excerpts, credentials, infrastructure addresses or internal manuals. The existing simulator's THIRD_PARTY_NOTICES.md explicitly does not grant permission to redistribute proprietary components. Choose a license for the newly authored code only; sponsor runtimes retain their own terms. An open-source client does not make sponsor services open source or guarantee zero operating cost.

## Prior-work disclosure draft


## Acceptance criteria

- Clean documented setup and reproducible synthetic fixtures.
- Actual Zetaris query and Meterless execution recorded; a local fixture mode must be labelled and cannot establish sponsor compliance.
- Known incident produces a hypothesis citing valid evidence IDs.
- Unrelated events do not become supporting citations.
- Missing or contradictory evidence produces uncertainty or abstention.
- Provider failures remain visible; no silent simulated success.
- No API keys committed or exposed in demo/trace.
- Video 1–4 minutes, slides, source repository and setup README.

## Open dependencies


## Sources

- Event and official rules: https://hackathon.genai.works/event/open-agent-hackathon-2026
- Meterless integration overview: https://meterless.ai/how-it-works.html
- Meterless CLI and API reference: https://meterless.ai/cli.html
- Zetaris product and connection documentation links: https://www.zetaris.com/
