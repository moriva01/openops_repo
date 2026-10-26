"""Recompute all sample outputs and traces without providers, credentials or third-party packages."""
import json
from pathlib import Path
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'apps'/'openops'))
from receiver.sample_runner import run_case


def main():
    paths=sorted((root/'input_examples').glob('*.json'))
    if len(paths)!=3:raise ValueError('Expected exactly three bundled cases')
    with tempfile.TemporaryDirectory() as folder:
        for path in paths:
            case=json.loads(path.read_text(encoding='utf-8'))
            actual=run_case(case,Path(folder)/'logs')
            expected=json.loads((root/'output_examples'/path.name).read_text(encoding='utf-8'))
            if actual!=expected:raise ValueError('Output drift: '+path.name)
            trace_name=Path(actual['log_file']).name
            if (Path(folder)/'logs'/trace_name).read_bytes()!=(root/'output_examples'/'logs'/trace_name).read_bytes():
                raise ValueError('Trace drift: '+path.name)
            print('PASS:',case['case_id'],'|',actual['report']['status'],'| monitor:',actual['monitor']['final_state'],
                  '| scripted calls:',len(actual['manifest']['model_calls']),'| external requests: 0')
    print('PASS: all committed outputs and JSONL traces reproduced exactly')


if __name__=='__main__':main()
