# Offline examples and judge-facing entry point

## What this mode proves

Sample mode demonstrates the actual monitoring state machine, shared bounded investigation orchestration, World Model ingest/context services, citation checking, revision path and abstention behavior. It uses SQLite and Python's standard library. It needs no PostgreSQL server, credentials, local GPU, Zetaris, Nightshift, NVIDIA endpoint, external notification or production data.

**Generation is an authored fixture, not AI inference.** The output and every trace identify `offline_fixture`. No provider receipts, token usage or live sponsor calls are fabricated. This mode is separate from the production console; it never activates automatically after an outage. Successful offline examples do not establish live integration or model accuracy.

## Run from a clean source checkout

Prerequisite: Python 3.9 or newer, including the standard SQLite module. No `pip install` is needed for this path.

From the repository root:

```bash
python run.py --sample --all --quiet-trace
```

This returns structured JSON and writes the three results to `.local/sample-results/`, with matching JSONL under `.local/sample-results/logs/`. Omit `--quiet-trace` to print JSONL progress to stderr while keeping stdout valid result JSON.

Single input:

```bash
python run.py --sample --input input_examples/01_voice_output_blocked.json --output .local/voice-result.json --quiet-trace
```

Its default trace directory is `.local/logs/`, relative to the selected output file. `--log-dir` can override the physical trace directory; the result's `log_file` remains a logical `logs/<run-id>.jsonl` reference mapped to that directory.

Environment alternative in PowerShell:

```powershell
$env:SAMPLE_MODE = 'true'
python run.py --all --quiet-trace
```

Explicit `--sample` is portable across shells. Without that flag or `SAMPLE_MODE=true`, the root runner exits instead of attempting live operation. The live application continues to use `apps/openops/compose.yaml`; setting the root sample flag does not reconfigure a running receiver.

Use `--input -` to read a JSON request from stdin. Invalid requests return structured error JSON with `status: error`, `report: null` and nonzero exit status. Input size, observation count, evidence queries and generation-role calls are bounded.

## Verify outputs, not just startup

```bash
python tools/verify_examples.py
python -S -m unittest discover -s tests -v
```

`verify_examples.py` recomputes each result and compares both JSON and JSONL with the committed examples. `-S` disables third-party site packages for the standard-library-only tests. One CLI regression test denies socket operations and subprocess execution through a Python audit hook and excludes provider settings from the child environment. It also verifies that live database/provider/notification modules were never imported.

The fixtures cover:

| Case | Monitor | Scripted calls | Accepted report |
|---|---|---:|---|
| VOICE disabled with healthy processes/resources | Opens, recovers, returns normal | 3 | Configuration-linked hypothesis, scoped to observations |
| CPU pressure with an availability distractor | Opens and recovers | 5 | Initial overclaim rejected, one revision accepted |
| Missing cause evidence | Opens and remains firing | 3 | Insufficient evidence, no causal hypothesis |

Every citation is resolved from actual loaded context. Changing a fixture so a cited condition disappears produces an error, not an unchanged canned citation. Scripted critique still is not independent model reasoning; live validation is documented separately.

## Docker without network at runtime

Build once from the repository root:

```bash
docker build -f Dockerfile.sample -t openops-sample .
```

The base image must be available locally or downloaded during build. The sample image installs no third-party Python packages and excludes credentials and live provider adapters from its build context.

Run all examples with network disabled and a read-only root filesystem:

```bash
docker run --rm --network none --read-only --tmpfs /app/.local:rw,uid=10001,gid=10001,size=16m openops-sample
```

Outputs are printed as JSON; temporary in-container files disappear when the container is removed. Use a deliberately private volume instead of tmpfs if artifacts must persist. This command does not stop or alter the monitoring lab, provider services or notification connectors.

## Shared implementation and storage

`monitor_logic.py` contains the pure state/severity transitions used by both live evaluation and samples. `investigation_engine.py` contains the bounded planner/investigator/evaluator sequence, required-evidence policy, validation and revision logic. The live `investigation.py` supplies PostgreSQL, Zetaris, Nightshift and durable run/trace adapters. The offline runner supplies synthetic tool rows and a disclosed scripted generator.

The same World Model services run against PostgreSQL live and SQLite offline. Stable IDs, typed normalization, atomic/idempotent ingest, incident memberships, topology and bounded context remain shared. SQLite foreign keys are enabled. The default sample store is in memory; `--world-db .local/sample-world.sqlite3` can retain offline world state without connecting to the production database. Counts in a persistent store include other retained sample contexts.

The bundled fixtures and results are MIT-licensed original synthetic data. No production identity mapping or private runtime trace is required. Live integration evidence, including real NVIDIA receipts and actual Teams delivery, remains distinct in the earlier validation guides.
