"""Synthetic mode reuses real contracts and cannot access providers or production state."""
import copy
import json
from pathlib import Path
import socket
import subprocess
import os
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'apps'/'openops'))
from receiver.sample_runner import run_case, validate_case
from receiver.world_model import WorldStoreService, IngestPipelineService, ContextBuilderService


def examples():
    root = Path(__file__).resolve()
    for parent in root.parents:
        if (parent / 'input_examples').is_dir():
            return sorted((parent / 'input_examples').glob('*.json'))
    raise RuntimeError('Synthetic input bundle not found')


class SampleTests(unittest.TestCase):
    def cases(self):
        paths = examples()
        self.assertEqual(len(paths), 3)
        return [json.loads(p.read_text(encoding='utf-8')) for p in paths]

    def test_three_cases_no_network_and_expected_outcomes(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(socket, 'socket', side_effect=AssertionError('Network prohibited')):
            for case in self.cases():
                with self.subTest(case=case['case_id']):
                    result = run_case(case, folder)
                    expected = case['expected']
                    self.assertEqual(result['report']['status'], expected['report_status'])
                    self.assertEqual(result['monitor']['final_state'], expected['monitor_final_state'])
                    self.assertEqual(len(result['manifest']['model_calls']), expected['fixture_calls'])
                    self.assertEqual(result['manifest']['external_requests'], 0)
                    self.assertEqual(result['manifest']['live_integrations_used'], [])
                    self.assertTrue(all(c['receipt_id'] is None for c in result['manifest']['model_calls']))
                    known = {e['evidence_id'] for e in result['report']['evidence']}
                    for h in result['report']['hypotheses'] + result['report']['alternatives']:
                        self.assertTrue(set(h['evidence_ids']) <= known)

    def test_cpu_revision_is_executed_and_logged(self):
        with tempfile.TemporaryDirectory() as folder:
            result = run_case(self.cases()[1], folder)
            log = Path(folder, Path(result['log_file']).name)
            entries = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
            self.assertIn('report.revision_requested', [e['action'] for e in entries])
            self.assertEqual(result['manifest']['model_calls'][-1]['role'], 'final_evaluator')
            self.assertIn('do not prove', result['report']['summary'])

    def test_unknown_cause_never_clears_active_incident(self):
        with tempfile.TemporaryDirectory() as folder:
            result = run_case(self.cases()[2], folder)
            self.assertEqual(result['report']['hypotheses'], [])
            self.assertEqual(result['report']['review']['verdict'], 'insufficient')
            self.assertEqual(result['monitor']['final_state'], 'firing')
            self.assertFalse(any(e['transition'] == 'resolved' for e in result['monitor']['history']))

    def test_output_is_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            case = self.cases()[0]
            a, b = run_case(case, first), run_case(case, second)
            self.assertEqual(a, b)
            self.assertEqual(Path(first, Path(a['log_file']).name).read_bytes(), Path(second, Path(b['log_file']).name).read_bytes())

    def test_changed_evidence_cannot_receive_a_canned_citation(self):
        case = self.cases()[0]
        for row in case['observations']:
            row['voice_output_enabled'] = True
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'no observed match'):
                run_case(case, folder)

    def test_non_synthetic_or_duplicate_observations_rejected(self):
        case = self.cases()[0]
        case['provenance']['kind'] = 'live'
        with self.assertRaises(ValueError):
            validate_case(case)
        case = self.cases()[0]
        case['observations'][1]['event_id'] = case['observations'][0]['event_id']
        with self.assertRaises(ValueError):
            validate_case(case)

    def test_sqlite_world_ingest_rollback_and_idempotency(self):
        store = WorldStoreService.sqlite()
        try:
            store.initialize()
            pipeline = IngestPipelineService(store)
            row = self.cases()[0]['observations'][0]
            bad = {**row, 'event_id': self.cases()[0]['observations'][1]['event_id'], 'observed_epoch': 'invalid'}
            with self.assertRaises(ValueError):
                with store.db:
                    pipeline.ingest('sample', 'synthetic', 'timeline', [row, bad])
            self.assertEqual(store.execute('SELECT count(*) n FROM wm_observations').fetchone()['n'], 0)
            for _ in range(2):
                with store.db:
                    pipeline.ingest('sample', 'synthetic', 'timeline', [row])
            self.assertEqual(store.execute('SELECT count(*) n FROM wm_observations').fetchone()['n'], 1)
            self.assertEqual(ContextBuilderService(store).build('other', row['observed_epoch'])['evidence'], [])
        finally:
            store.db.close()

    def test_cli_runs_with_standard_library_and_network_audit_denied(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            code="""import sys,runpy
def deny(event,args):
    if event.startswith('socket.') or event in ('os.system','subprocess.Popen'):
        raise RuntimeError('Network and subprocess access forbidden in sample mode')
sys.addaudithook(deny)
entry=runpy.run_path(sys.argv[1],run_name='sample_entry')
sys.argv=[sys.argv[1],'--all','--quiet-trace','--output-dir',sys.argv[2]]
code=entry['main']()
assert not {'psycopg','receiver.server','receiver.zetaris','receiver.nightshift','receiver.notifications'} & set(sys.modules)
raise SystemExit(code)
"""
            env={k:v for k,v in os.environ.items() if k in ('SystemRoot','WINDIR','PATH','TEMP','TMP')}
            env.update(SAMPLE_MODE='true',PYTHONUTF8='1')
            result=subprocess.run([sys.executable,'-S','-c',code,str(root/'run.py'),folder],capture_output=True,text=True,env=env,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            output=json.loads(result.stdout)
            self.assertEqual(len(output['results']),3)

    def test_cli_invalid_input_returns_structured_error(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            result=subprocess.run([sys.executable,'-S',str(root/'run.py'),'--sample','--input','-',
                                   '--quiet-trace','--output-dir',folder],input='{}',capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,1)
            output=json.loads(result.stdout)
            self.assertEqual(output['status'],'error')
            self.assertIsNone(output['report'])

    def test_committed_examples_match_computation(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            for path in examples():
                case=json.loads(path.read_text(encoding='utf-8'))
                actual=run_case(case,folder)
                expected=json.loads((root/'output_examples'/path.name).read_text(encoding='utf-8'))
                self.assertEqual(actual,expected)
