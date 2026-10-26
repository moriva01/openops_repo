"""Offline synthetic cases using the real orchestration and World Model, with scripted generation."""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import uuid

from receiver.investigation_engine import TOOLS, execute
from receiver.monitor_logic import SEVERITIES, next_state, severity_for
from receiver.world_model import WorldStoreService, IngestPipelineService, ContextBuilderService

DISCLOSURE = ('OFFLINE SYNTHETIC DEMONSTRATION. Generation responses are authored fixtures, not live AI. '
              'No Zetaris, Nightshift, NVIDIA, external notification or production database is contacted.')


def validate_case(case):
    if not isinstance(case, dict) or case.get('schema') != 'openops.offline_case.v1':
        raise ValueError('Expected openops.offline_case.v1')
    if not isinstance(case.get('case_id'), str) or not re.fullmatch(r'[a-z0-9_-]{1,60}', case['case_id']):
        raise ValueError('Invalid case ID')
    if case.get('provenance', {}).get('kind') != 'synthetic':
        raise ValueError('Sample mode accepts explicitly synthetic fixtures only')
    monitor = case.get('monitor', {})
    if monitor.get('metric') not in ('voice_pending', 'cpu_percent', 'memory_percent', 'disk_percent'):
        raise ValueError('Unsupported sample metric')
    if monitor.get('comparator', 'above') not in ('above', 'below') or monitor.get('severity') not in SEVERITIES:
        raise ValueError('Invalid monitor condition')
    threshold = monitor.get('threshold')
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or threshold < 0:
        raise ValueError('Invalid threshold')
    if type(monitor.get('duration_seconds')) is not int or not 0 <= monitor['duration_seconds'] <= 3600:
        raise ValueError('Invalid duration')
    if type(monitor.get('recovery_samples')) is not int or not 1 <= monitor['recovery_samples'] <= 20:
        raise ValueError('Invalid recovery count')
    if not isinstance(monitor.get('name'), str) or not 1 <= len(monitor['name']) <= 120:
        raise ValueError('Invalid monitor name')
    rows = case.get('observations')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 30:
        raise ValueError('Use 1..30 observations')
    allowed = {'event_id', 'observed_epoch'} | {k for columns in TOOLS.values() for k in columns}
    ids, previous = set(), None
    for row in rows:
        if not isinstance(row, dict) or set(row) - allowed:
            raise ValueError('Unknown observation field')
        event = str(uuid.UUID(row['event_id']))
        observed = row['observed_epoch']
        if event != row['event_id'] or event in ids:
            raise ValueError('Use distinct canonical source event UUIDs')
        if type(observed) not in (int, float) or not math.isfinite(observed) or observed <= 0:
            raise ValueError('Invalid observation time')
        if previous is not None and observed <= previous:
            raise ValueError('Observations must be strictly ordered')
        for key, value in row.items():
            if key not in ('event_id', 'observed_epoch') and value is not None:
                if not isinstance(value, (str, int, float, bool)) or isinstance(value, str) and len(value) > 120:
                    raise ValueError('Invalid observation value')
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError('Non-finite observation')
        ids.add(event)
        previous = observed
    if not isinstance(case.get('scripted_responses'), dict) or not isinstance(case.get('evidence_selectors'), dict):
        raise ValueError('Scripted responses and evidence selectors required')
    return case


class FixtureGenerator:
    """An explicitly scripted test double; never a model or a provider fallback."""
    def __init__(self, case, note):
        self.case, self.note, self.calls = case, note, []

    def generate(self, role, payload, deadline):
        if role not in self.case['scripted_responses']:
            raise ValueError('No scripted response for role ' + role)
        context = payload.get('context', {})

        def resolve(value):
            if isinstance(value, str) and value.startswith('$evidence:'):
                name = value.split(':', 1)[1]
                selector = self.case['evidence_selectors'].get(name)
                if not isinstance(selector, dict):
                    raise ValueError('Unknown evidence selector')
                for evidence in context.get('evidence', []):
                    def matches(key, expected):
                        actual = evidence['facts'].get(key)
                        return actual == expected and (type(actual) is bool) == (type(expected) is bool)
                    if evidence['tool'] == selector['tool'] and all(matches(k, v) for k, v in selector['facts'].items()):
                        return evidence['evidence_id']
                raise ValueError('Fixture evidence selector has no observed match: ' + name)
            if isinstance(value, dict):
                return {k: resolve(v) for k, v in value.items()}
            if isinstance(value, list):
                return [resolve(v) for v in value]
            return value

        result = resolve(copy.deepcopy(self.case['scripted_responses'][role]))
        self.calls.append({'role': role, 'model': 'scripted-fixture', 'provider': 'offline-fixture',
                           'receipt_id': None, 'live_generation': False})
        self.note('fixture.response_loaded', {'role': role, 'scripted': True,
                                            'context_evidence_count': len(context.get('evidence', []))})
        return result


def lifecycle(case):
    settings = case['monitor']
    monitor = {**settings, 'state': 'normal', 'condition_since': None, 'recovery_count': 0,
               'last_observed': None}
    history, opening = [], None
    for row in case['observations']:
        value = row.get(settings['metric'])
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('Sample monitor metric is unavailable')
        if settings['metric'] == 'voice_pending' and row.get('app_reachable') is not True:
            raise ValueError('Voice monitoring requires an observed reachable application')
        severity = severity_for(monitor, value)
        transition = {**monitor, 'threshold': 0}
        state, since, count, action = next_state(transition, 1 if severity else 0, row['observed_epoch'])
        monitor.update(state=state, condition_since=since, recovery_count=count, last_observed=row['observed_epoch'])
        item = {'source_event_id': row['event_id'], 'observed_epoch': row['observed_epoch'], 'value': value,
                'state': state, 'transition': action, 'severity': 'clear' if action == 'resolved' else severity}
        history.append(item)
        if action == 'opened' and opening is None:
            opening = {'host_id': 'synthetic-server-01', 'event_id': row['event_id'], 'observed_epoch': row['observed_epoch'],
                       'value': value, 'threshold': settings['threshold'], 'metric': settings['metric']}
    if opening is None:
        raise ValueError('Fixture contains no sustained violation; no incident can be investigated')
    return opening, {'final_state': monitor['state'], 'history': history, 'notifications_sent': 0,
                     'remediation_executed': False}


def run_case(case, log_dir, world_db=':memory:', emit=None):
    validate_case(case)
    canonical = json.dumps(case, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    fingerprint = hashlib.sha256(canonical).hexdigest()
    run_id = 'sample_' + case['case_id'] + '_' + fingerprint[:12]
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / (run_id + '.jsonl')
    trace = []

    def note(action, detail):
        entry = {'schema': 'openops.sample_trace.v1', 'run_id': run_id, 'step': len(trace) + 1,
                 'mode': 'offline_fixture', 'action': action, 'detail': detail}
        trace.append(entry)
        with log_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(entry, sort_keys=True, allow_nan=False) + '\n')
        if emit:
            emit(entry)

    log_path.write_text('', encoding='utf-8')
    store = None
    try:
        note('sample.started', {'disclosure': DISCLOSURE, 'input_sha256': fingerprint})
        opening, monitor_result = lifecycle(case)
        note('monitor.lifecycle_evaluated', monitor_result)
        store = WorldStoreService.sqlite(world_db)
        store.initialize()
        pipeline, builder = IngestPipelineService(store), ContextBuilderService(store)
        query_count = 0

        def query(tool, host, start, end, deadline):
            nonlocal query_count
            query_count += 1
            if query_count > 3 or tool not in TOOLS:
                raise ValueError('Fixture tool budget exceeded')
            rows = [{'event_id': r['event_id'], 'observed_epoch': r['observed_epoch'],
                     **{k: r.get(k) for k in TOOLS[tool]}} for r in case['observations']
                    if start <= r['observed_epoch'] <= end][:30]
            note('fixture.tool_read', {'tool': tool, 'rows': len(rows), 'start_epoch': start, 'end_epoch': end,
                                       'source_event_ids': [r['event_id'] for r in rows], 'external_query': False})
            return rows

        def ingest(context_id, host, tool, rows):
            with store.db:
                return pipeline.ingest(context_id, host, tool, rows)

        generator = FixtureGenerator(case, note)
        alert = {'metric': case['monitor']['metric'], 'opening_evidence': opening}
        result = execute(alert, run_id, 1, generator, query, ingest, builder.build, note,
                         now=opening['observed_epoch'] + 120, source_name='synthetic-fixture',
                         provider_name='scripted-fixture', requested_model='scripted-fixture')
        note('investigation.finished', {'status': result['status'], 'verdict': result['report']['review']['verdict'],
                                       'model_calls': len(generator.calls)})
        counts = {name: store.execute('SELECT count(*) AS n FROM ' + name).fetchone()['n']
                  for name in ('wm_entities', 'wm_contexts', 'wm_observations', 'wm_memberships', 'wm_edges')}
        result['manifest'].update(mode='offline_fixture', synthetic_data=True, live_integrations_used=[],
                                  external_requests=0, notifications_sent=0, storage='sqlite',
                                  world_store_counts=counts)
        output = {'schema': 'openops.sample_result.v1', 'mode': 'offline_fixture', 'case_id': case['case_id'],
                  'run_id': run_id, 'input_sha256': fingerprint, 'disclosure': DISCLOSURE, **result,
                  'monitor': monitor_result, 'log_file': 'logs/' + log_path.name}
        note('sample.finished', {'status': result['status'], 'report_status': result['report']['status'],
                                 'tool_queries': query_count, 'fixture_calls': len(generator.calls)})
        output['trace_steps'] = len(trace)
        return output
    except (ValueError, KeyError, TypeError, OverflowError) as error:
        note('sample.failed', {'error_type': type(error).__name__, 'message': str(error)[:250]})
        raise
    finally:
        if store is not None:
            store.db.close()
