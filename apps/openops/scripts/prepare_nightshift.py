"""Configure this local Windows runtime without printing its token."""
import os
import argparse
from pathlib import Path

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--model',help='Available Nightshift route or discovered model ID')
args=parser.parse_args()
token_path=Path(os.environ["LOCALAPPDATA"])/"ai.meterless.runtime/proxy-token"
if not token_path.is_file():
    raise SystemExit("Runtime token is not at its documented path. Configure .local/nightshift.env privately from nightshift.env.example.")
token=token_path.read_text().strip()
if not token:
    raise SystemExit("Runtime token is empty")
destination=root/".local/nightshift.env"
destination.parent.mkdir(exist_ok=True)
existing=dict(line.split('=',1) for line in destination.read_text().splitlines() if '=' in line) if destination.exists() else {}
model=args.model or existing.get('METERLESS_MODEL','meterless/fast')
if not model or len(model)>200 or any(c in model for c in '\r\n'):
    raise SystemExit('Invalid model identifier')
destination.write_text("METERLESS_BASE_URL=http://host.docker.internal:8088/v1\nMETERLESS_RUNTIME_TOKEN="+token+"\nMETERLESS_MODEL="+model+"\n")
print("Nightshift connection prepared; credential omitted. No NVIDIA key was read.")
