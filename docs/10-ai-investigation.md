# Meterless investigation and shared world state

## What runs

OpenOps runs a background investigation worker independently of browser activity. Recent active alerts are queued automatically. An operator can also select **Investigate** on an existing alert, including a resolved one. A resolved alert is analyzed as a historical incident; the report does not imply a current failure.

The worker retrieves evidence through Zetaris, ingests it through a minimal implementation of the Meterless World Model reference architecture, and calls models through Meterless Nightshift. It does not execute repairs, shell commands or model-generated SQL.

## Execution sequence

1. Queue one active investigation per alert. Repeated requests reuse its run ID. Explicit New analysis preserves earlier reports, with at most three runs per alert.
2. Claim the queued job using a PostgreSQL row lock and persist its running state.
3. Retrieve the incident timeline through Zetaris in a window extending 120 seconds before and at most 120 seconds after the opening observation.
4. Ingest immutable, source-linked observations into the World Model.
5. Build a small context for a planner. The planner selects up to two additional tools from a closed list. An explicit evidence policy requires portal/process state for voice backlog, or host resources for other metrics; the trace distinguishes model choices from this policy.
6. Retrieve those facts through Zetaris and build the grounded investigation context.
7. An investigator proposes explanations, alternatives, missing evidence and read-only next checks.
8. Validate report structure and ensure citations refer to loaded evidence.
9. An evaluator inspects whether the cited facts actually support the statements. One revision and one final evaluation are allowed.
10. Persist the result, evaluator verdict, model receipts, context manifest and execution trace. Unresolved evaluator objections produce `needs_review`, not silent acceptance.

If the evaluator finds insufficient support, the report is labelled `insufficient_evidence`. Citation validity is a structural check, not proof of factual entailment; model critique remains fallible. Reports are hypotheses for operator review.

## Evidence tools

| Tool | Facts |
|---|---|
| `timeline` | Voice pending, pending age, throughput, application reachability |
| `portal_services` | Voice/SMS/data output enablement, other queues, API/mediation/delivery process state |
| `host_resources` | CPU, memory and disk utilization |
| `traffic` | Per-channel queues, throughput and rejection total |

Each query uses fixed identifiers/columns and a bounded host/time filter with at most 30 rows. The model chooses a tool name, not SQL text. There are at most three evidence queries per attempt. This investigation path uses `openops_pg.monitor_samples`; chart history still reads application PostgreSQL directly.

## World Model implementation

Implemented services:

- `WorldStoreService`: PostgreSQL schema version, entities, contexts, immutable observations, memberships, typed relationships and ingest-job records.
- `IngestPipelineService`: stable content-derived IDs, typed fact normalization, domain classification, attributed contexts and idempotent transactional writes. Failed ingest can be resumed safely.
- `ContextBuilderService`: per-attempt incident membership isolation, observation-time relevance, continuity anchors, structured evidence and a size budget. Agents actually consume this output.

Relationships such as `runs_on` and `part_of` describe declared application topology; they are not inferred causal links. Shared observations can belong to several incident contexts without duplicate records. Derived context is reconstructed on read.

This is a **minimal reference-architecture adaptation**, not the complete engine feature catalog. The manifest explicitly excludes vector memory, autonomous repair, enrichment queues and world migrations. Ingest stage metadata describes implemented operations and deferred/on-read operations separately; it does not claim all advanced stages exist.

Tables: `wm_schema`, `wm_entities`, `wm_contexts`, `wm_observations`, `wm_memberships`, `wm_edges`, `wm_ingest_jobs`. Investigation state uses `investigations` and `investigation_trace`.

## Nightshift setup

On the Windows monitoring host, start Nightshift and configure its model provider in the application. NVIDIA credentials stay in Nightshift Providers. OpenOps needs only a Runtime URL, Runtime token and available route/model ID.

From `apps/openops`:

```powershell
python scripts/prepare_nightshift.py --model nvidia/nemotron-3.5-bolt-e4b
docker compose up -d --build
docker compose exec -T receiver python -m receiver.setup_data
```

The model ID above was available in the lab; discover and select a model present in your runtime rather than assuming availability. `--model` is optional and preserves an existing selection. The script reads the documented local runtime-token file and writes `.local/nightshift.env` without printing the token. For another runtime, configure that private file from `nightshift.env.example`.

Docker uses `http://host.docker.internal:8088/v1`, Bearer authentication, `meterless-app: openops-evidence` and `meterless-scope: user`. Requests use the OpenAI-compatible chat endpoint and JSON output. Actual routed model, provider, receipt ID, usage and latency are retained for completed calls. A requested model is not treated as proof of which model served a call.

Preparation creates an empty Runtime-token setting if no configuration exists. An unconfigured/unreachable provider produces an error, not a simulated report. Set `OPENOPS_INVESTIGATION_ENABLED=false` in the monitoring environment to disable the worker; the deterministic monitor continues.

## Limits and failures

- 200-second attempt budget, up to five model calls, and at most one report revision.
- Model requests time out after at most 40 seconds or the remaining attempt budget.
- No automatic retry after an uncertain model response; upstream work may continue after a client timeout.
- A failed/interrupted investigation can be retried explicitly, with a total limit of three attempts per run. Earlier traces remain visible.
- A running job left behind by a crashed worker is marked interrupted after five minutes. It is not silently replayed.
- Traces record selected tools, loaded context, model outputs/receipts and failures. Outputs are untrusted data and are rendered as text.
- Raw hostnames, host IDs, subscriber records, environment snapshots and credentials are not sent in the model context. Public entity anchors are content-derived IDs with neutral labels.

## API and portal

- `POST /api/investigations/start`, authenticated user session or user-owned token: `{"alert_id":1,"retry":true}`. Use `new_run:true` explicitly to preserve the completed report and create another analysis.
- `GET /api/investigations/<run_id>`, authenticated user session or user-owned token: state, report, manifest and ordered trace.
- `GET /api/world/<run_id>`, authenticated user session or user-owned token: bounded structured world context.
- `/api/dashboard` includes recent investigation summaries.

In Alerts, open **Details** and select **Investigate / retry**. The alert details dialog shows status and report details, source IDs, missing evidence, evaluator findings and the execution trace. `error`, `interrupted` and `needs_review` remain visibly distinct from `completed`.

Logs are written to stdout and `openops-logs` as `/app/logs/<run_id>.jsonl`, with matching database trace rows. Provider credentials are never written to those logs. Opt-in notification connectors and role-based console access are described in [console administration](11-console-and-administration.md).
