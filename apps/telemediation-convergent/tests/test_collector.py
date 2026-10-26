import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from telemediation.collector import Spool, cpu_counters, cpu_percent, memory_metrics, transmit


class CollectorTests(unittest.TestCase):
    def test_cpu_ignores_guest_double_counting(self):
        self.assertEqual(cpu_counters('cpu 10 0 10 70 10 0 0 0 8 0\n'), (100, 80))
        self.assertEqual(cpu_percent((100, 80), (200, 100)), 80)
        self.assertIsNone(cpu_percent((100, 80), (100, 80)))

    def test_memory_uses_available_not_just_free(self):
        result = memory_metrics('MemTotal: 1000 kB\nMemAvailable: 400 kB\nMemFree: 100 kB\n')
        self.assertEqual(result['used_percent'], 60)
        self.assertEqual(result['available_bytes'], 409600)

    def test_durable_spool_retention_and_partial_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'spool.sqlite3'
            spool = Spool(path, limit=2)
            self.assertEqual(spool.add({'event_id': 'a'}), 0)
            spool.add({'event_id': 'b'})
            self.assertEqual(spool.add({'event_id': 'c'}), 1)
            spool.close()
            spool = Spool(path, limit=2)
            try:
                self.assertEqual([p['event_id'] for p in spool.batch()], ['b', 'c'])
                spool.acknowledge(['b'])
                self.assertEqual(spool.batch(), [{'event_id': 'c'}])
            finally:
                spool.close()

    def test_failed_send_keeps_event_for_retry_and_acks_only_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            spool = Spool(Path(tmp) / 'queue.sqlite3')
            try:
                spool.add({'event_id': 'a'})
                spool.add({'event_id': 'b'})
                with patch('urllib.request.urlopen', side_effect=OSError('offline')):
                    with self.assertRaises(OSError):
                        transmit(spool, 'http://127.0.0.1/ingest', 'test-only')
                self.assertEqual(spool.count(), 2)
                with patch('urllib.request.urlopen') as request:
                    request.return_value.__enter__.return_value.read.return_value = json.dumps({'accepted_event_ids': ['a', 'not-sent']}).encode()
                    self.assertEqual(transmit(spool, 'http://127.0.0.1/ingest', 'test-only'), 1)
                self.assertEqual(spool.batch(), [{'event_id': 'b'}])
            finally:
                spool.close()
