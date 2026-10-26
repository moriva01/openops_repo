# Synthetic input examples

These three cases are original, hand-authored synthetic data licensed under the [OpenOps MIT license](../apps/openops/LICENSE). They contain no captured infrastructure identities, subscriber data, provider credentials or production logs. Observation event UUIDs are deterministically generated synthetic identifiers.

| Input | Demonstrates | Expected final result |
|---|---|---|
| [01_voice_output_blocked.json](01_voice_output_blocked.json) | Sustained queue, disabled VOICE output, active delivery process and healthy sampled resources; subsequent healthy recovery | Supported hypothesis; monitor normal |
| [02_cpu_pressure.json](02_cpu_pressure.json) | High CPU with available application; evaluator rejects a causal overclaim and requests one revision | Narrowed resource-pressure hypothesis; monitor normal |
| [03_insufficient_evidence.json](03_insufficient_evidence.json) | Sustained backlog without portal, service or resource evidence | Insufficient evidence; monitor remains firing |

Each JSON file contains monitor settings, time-ordered observations, evidence selectors and **authored scripted responses**. These responses are fixture inputs, not recorded NVIDIA generations. The CPU case intentionally includes an incorrect initial draft so the shared bounded revision path can be inspected. The final output must be read with its evaluator result; initial drafts in traces are not accepted conclusions.

The fixture generator resolves citation selectors against context produced by the real World Model. A missing match fails rather than inventing a citation. The source, disclosure and provider metadata remain explicitly offline.

From the repository root:

```bash
python run.py --sample --all --quiet-trace
python tools/verify_examples.py
```

Full instructions: [offline judging guide](../docs/15-offline-examples.md). The paired results and synthetic JSONL traces are in [output_examples](../output_examples/README.md).
