import tempfile
import os
import unittest
from unittest.mock import patch
from receiver.webhook_demo import connection, accept


class InboxTests(unittest.TestCase):
    def test_opening_recovery_and_deduplicated_retries(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'WEBHOOK_DEMO_DB': folder + '/inbox.sqlite3'}):
            with connection() as db:
                opened = {'schema': 'openops.notification.v1', 'alert_id': 42, 'action': 'opened', 'severity': 'warning', 'evidence': {'value': 1.0}}
                self.assertTrue(accept(db, 'delivery-1', opened))
                self.assertFalse(accept(db, 'delivery-1', opened))
                self.assertFalse(accept(db, 'delivery-1', {**opened, 'evidence': {'value': 1}}))
                with self.assertRaises(ValueError):
                    accept(db, 'delivery-1', {**opened, 'evidence': {'value': True}})
                resolved = {**opened, 'action': 'resolved', 'severity': 'clear'}
                self.assertTrue(accept(db, 'delivery-2', resolved))
                self.assertEqual(db.execute('SELECT count(*) FROM receipts').fetchone()[0], 2)
                with self.assertRaises(ValueError):
                    accept(db, 'delivery-1', resolved)

    def test_rejects_missing_identity_or_wrong_schema(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'WEBHOOK_DEMO_DB': folder + '/inbox.sqlite3'}):
            with connection() as db:
                for key, payload in [(None, {}), ('a', {'schema': 'unknown'}), ('b', {'schema': 'openops.notification.v1', 'action': 'opened'})]:
                    with self.assertRaises(ValueError):
                        accept(db, key, payload)
