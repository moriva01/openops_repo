import copy
import os
import time
import unittest
import uuid
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from receiver.monitoring import initialize, evaluate, acknowledge, configure


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.schema = "test_monitor_" + uuid.uuid4().hex
        self.db = psycopg.connect(row_factory=dict_row)
        self.db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.db.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
        initialize(self.db)
        self.now = time.time()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def sample(self, offset, value, **fields):
        return {"event_id":str(uuid.uuid4()),"host_id":"test", "observed_epoch":str(self.now+offset),
                "voice_pending":str(value),"app_reachable":"true",**fields}

    def step(self, offset, value):
        row = self.sample(offset,value)
        evaluate(self.db,row,self.now+offset)
        return row

    def monitor(self):
        return self.db.execute("SELECT * FROM monitors").fetchone()

    def test_sustained_violation_acknowledgement_and_distinct_recovery(self):
        for offset in (0,15,30,45):
            self.step(offset,3)
        self.assertEqual(self.monitor()["state"],"pending")
        self.step(60,3)
        aid = self.db.execute("SELECT id FROM alerts").fetchone()["id"]
        acknowledge(self.db,aid)
        self.assertEqual(self.monitor()["state"],"firing")
        row = self.step(75,0)
        evaluate(self.db,row,self.now+76)
        self.assertEqual(self.monitor()["recovery_count"],1)
        self.step(90,0)
        alert = self.db.execute("SELECT * FROM alerts").fetchone()
        self.assertIsNotNone(alert["acknowledged_at"])
        self.assertIsNotNone(alert["resolved_at"])
        actions = [r["action"] for r in self.db.execute("SELECT action FROM alert_history ORDER BY id")]
        self.assertEqual(actions,["opened","acknowledged","resolved"])

    def test_stale_sample_and_failed_query_never_resolve_open_alert(self):
        self.step(0,3)
        self.step(60,3)
        stale = self.sample(60,0)
        evaluate(self.db,stale,self.now+140)
        evaluate(self.db,None,self.now+150,"zetaris_HTTPError")
        self.assertEqual(self.monitor()["source_status"],"no_data")
        self.assertIsNone(self.db.execute("SELECT resolved_at FROM alerts").fetchone()["resolved_at"])

    def test_transient_violation_and_gap_reset_opening_duration(self):
        self.step(0,1)
        self.step(15,0)
        self.assertEqual(self.monitor()["state"],"normal")
        self.step(30,1)
        self.step(120,1)
        self.assertEqual(self.monitor()["state"],"pending")
        self.assertEqual(self.db.execute("SELECT count(*) n FROM alerts").fetchone()["n"],0)

    def test_disable_preserves_open_alert_and_blocks_redefinition(self):
        self.step(0,3)
        self.step(60,3)
        settings = dict(self.monitor())
        settings["enabled"] = False
        configure(self.db,settings)
        self.step(75,0)
        self.assertIsNone(self.db.execute("SELECT resolved_at FROM alerts").fetchone()["resolved_at"])
        settings["threshold"] = 10
        with self.assertRaises(ValueError):
            configure(self.db,settings)
