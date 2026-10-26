# Reproducible offline outputs

These results are computed from the [three synthetic inputs](../input_examples/README.md), using shared monitor transitions, the shared bounded investigation engine, real SQLite-backed World Model ingestion/context construction, citation validation and **scripted fixture responses**. They are not live model generations or demonstrations of live sponsor connectivity.

- [VOICE output blocked](01_voice_output_blocked.json): three scripted roles; supported hypothesis; recovery after two healthy samples.
- [CPU pressure](02_cpu_pressure.json): five scripted roles including a requested revision and final evaluation; application failure is not claimed in the accepted report.
- [Insufficient evidence](03_insufficient_evidence.json): explicit abstention; no invented cause or false recovery.

Each `log_file` resolves under this directory. The `logs/` folder contains only the authored synthetic runs. Runtime logs elsewhere remain ignored by Git. JSONL records include fixture tool reads, ingest stages, context construction, scripted role outputs, critique and final status. Step numbers replace wall-clock timestamps so both outputs and traces reproduce byte for byte. Observation times refer to the fixed synthetic fixture timeline, not to execution time.

Recompute and compare without changing published examples:

```bash
python tools/verify_examples.py
```

Regenerate intentionally after changing fixtures or shared behavior:

```bash
python run.py --sample --all --output-dir output_examples --quiet-trace
```

Default demonstration runs write under `.local/sample-results`, not here. Outputs and traces inherit the [OpenOps MIT license](../apps/openops/LICENSE). Live evidence remains separately documented in [webhook circuit validation](../docs/12-webhook-circuit-demo.md) and [Teams validation](../docs/13-outgoing-webhooks-and-teams.md).
