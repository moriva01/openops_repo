"""Judge-facing offline JSON entry point. Python standard library only."""
import argparse
import json
import os
from pathlib import Path
import sys
import sqlite3

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'apps' / 'openops'))
from receiver.sample_runner import run_case, DISCLOSURE


def main():
    parser = argparse.ArgumentParser(description='Run synthetic OpenOps cases without providers, credentials or network access.')
    parser.add_argument('--sample', action='store_true', help='Explicitly enable offline fixture mode')
    parser.add_argument('--input', help='Input JSON path, or - for stdin')
    parser.add_argument('--output', help='Write one JSON result to this path; stdout still returns JSON')
    parser.add_argument('--all', action='store_true', help='Run the three bundled cases')
    parser.add_argument('--output-dir', default='.local/sample-results')
    parser.add_argument('--log-dir', help='Trace directory; default <output-dir>/logs')
    parser.add_argument('--world-db', default=':memory:', help='Optional private SQLite database for persistent sample state')
    parser.add_argument('--quiet-trace', action='store_true', help='Keep stdout machine-readable and suppress JSONL stderr trace')
    args = parser.parse_args()
    if not args.sample and os.environ.get('SAMPLE_MODE', '').lower() != 'true':
        parser.error('Use --sample or SAMPLE_MODE=true. Live operation uses apps/openops/compose.yaml; there is no automatic fallback.')
    if args.all == bool(args.input) or args.all and args.output:
        parser.error('Choose --all or --input; --output applies only to a single input.')
    output_dir = Path(args.output).parent if args.output else Path(args.output_dir)
    log_dir = Path(args.log_dir) if args.log_dir else output_dir / 'logs'
    emit = None if args.quiet_trace else lambda entry: print(json.dumps(entry, sort_keys=True), file=sys.stderr)
    try:
        paths = sorted((ROOT / 'input_examples').glob('*.json')) if args.all else [args.input]
        results = []
        for source in paths:
            if str(source) == '-':
                raw = sys.stdin.read(131073)
            else:
                path = Path(source)
                if args.output and path.resolve() == Path(args.output).resolve():
                    raise ValueError('Input and output paths must differ')
                if path.stat().st_size > 131072:
                    raise ValueError('Input exceeds 128 KiB')
                raw = path.read_text(encoding='utf-8-sig')
            if len(raw.encode('utf-8')) > 131072:
                raise ValueError('Input exceeds 128 KiB')
            case = json.loads(raw)
            result = run_case(case, log_dir, args.world_db, emit)
            destination = output_dir / (Path(source).stem + '.json') if args.all else Path(args.output) if args.output else None
            if destination:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
            results.append(result)
        response = {'mode': 'offline_fixture', 'disclosure': DISCLOSURE, 'results': results} if args.all else results[0]
        print(json.dumps(response, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError, sqlite3.Error) as error:
        print(json.dumps({'mode': 'offline_fixture', 'status': 'error', 'report': None,
                          'error': {'type': type(error).__name__, 'message': str(error)[:250]}, 'disclosure': DISCLOSURE}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
