import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from receiver.world_model import WorldStoreService,IngestPipelineService,ContextBuilderService,stable_id
from receiver.investigation import validate_report,review_contract,initialize,enqueue,run
from receiver.monitoring import initialize as initialize_monitors


def report(eid):
    return {"status":"supported_hypothesis","summary":"The observed voice output was disabled while pending records accumulated.",
            "hypotheses":[{"title":"Output disabled","explanation":"The cited portal observation reports disabled output.",
                           "evidence_ids":[eid],"confidence":"medium"}],"alternatives":[],
            "missing_evidence":["No operator change audit was collected."],"recommended_checks":["Check the portal configuration with its operator."]}


class ReportTests(unittest.TestCase):
    def test_citation_must_reference_loaded_context(self):
        with self.assertRaises(ValueError):validate_report(report("invented"),{"evidence":[{"evidence_id":"known"}]})

    def test_supported_report_requires_cited_hypothesis(self):
        item=report("known");item["hypotheses"]=[]
        with self.assertRaises(ValueError):validate_report(item,{"evidence":[{"evidence_id":"known"}]})

    def test_insufficient_evidence_can_abstain(self):
        item=report("known");item.update(status="insufficient_evidence",hypotheses=[],summary="Available observations do not establish an explanation.")
        self.assertEqual(validate_report(item,{"evidence":[]})["status"],"insufficient_evidence")

    def test_evaluator_contract_is_closed(self):
        with self.assertRaises(ValueError):review_contract({"verdict":"definitely_causal","issues":[]})


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.db=psycopg.connect(row_factory=dict_row)
        self.schema="test_world_"+uuid.uuid4().hex
        self.db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.db.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
        self.store=WorldStoreService(self.db);self.store.initialize()
        self.row={"event_id":str(uuid.uuid4()),"observed_epoch":time.time(),"voice_pending":"2","app_reachable":"true"}

    def tearDown(self):
        self.db.rollback();self.db.close()

    def test_idempotent_ingest_and_grounded_context(self):
        pipeline=IngestPipelineService(self.store)
        first=pipeline.ingest("run-1","synthetic-host","timeline",[self.row])
        second=pipeline.ingest("run-1","synthetic-host","timeline",[self.row])
        self.assertEqual(first["observation_ids"],second["observation_ids"])
        self.assertEqual(self.db.execute("SELECT count(*) n FROM wm_observations").fetchone()["n"],1)
        context=ContextBuilderService(self.store).build("run-1",self.row["observed_epoch"])
        self.assertEqual(context["evidence"][0]["facts"]["voice_pending"],2)
        self.assertEqual(context["evidence"][0]["source_event_id"],self.row["event_id"])
        self.assertNotIn("synthetic-host",json.dumps(context))

    def test_shared_observation_is_not_duplicated_across_runs(self):
        pipeline=IngestPipelineService(self.store)
        pipeline.ingest("one","host","timeline",[self.row])
        pipeline.ingest("two","host","timeline",[self.row])
        self.assertEqual(self.db.execute("SELECT count(*) n FROM wm_observations").fetchone()["n"],1)
        self.assertEqual(self.db.execute("SELECT count(*) n FROM wm_memberships").fetchone()["n"],2)

    def test_failed_ingest_is_transactionally_resumable(self):
        bad={**self.row,"observed_epoch":"invalid","event_id":str(uuid.uuid4())}
        with self.assertRaises(ValueError):
            with self.db.transaction():IngestPipelineService(self.store).ingest("failed","host","timeline",[self.row,bad])
        self.assertEqual(self.db.execute("SELECT count(*) n FROM wm_observations").fetchone()["n"],0)
        IngestPipelineService(self.store).ingest("failed","host","timeline",[self.row])
        self.assertEqual(len(ContextBuilderService(self.store).build("failed",self.row["observed_epoch"])["evidence"]),1)

    def test_context_budget_and_cross_run_isolation(self):
        IngestPipelineService(self.store).ingest("one","host","timeline",[self.row])
        self.assertEqual(ContextBuilderService(self.store).build("other",time.time())["evidence"],[])
        context=ContextBuilderService(self.store).build("one",time.time(),budget=1)
        self.assertEqual(context["evidence"],[]);self.assertTrue(context["truncated"])


class FakeGenerator:
    def __init__(self,revise=False):self.calls=[];self.revise=revise
    def generate(self,role,payload,deadline):
        self.calls.append({"role":role,"model":"test-double","provider":"test-only"})
        if role=="planner":return {"tools":["portal_services"],"reason":"Check portal configuration and process state"}
        if "evaluator" in role:
            return {"verdict":"revise" if self.revise and role=="evaluator" else "supported","issues":["Clarify observed scope"] if self.revise else []}
        evidence=next(e for e in payload["context"]["evidence"] if e["tool"]=="portal_services")
        return report(evidence["evidence_id"])


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.schema="test_agent_"+uuid.uuid4().hex
        with psycopg.connect() as db:db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        with self.connection() as db:
            initialize_monitors(db);initialize(db)
            evidence={"host_id":"synthetic-host","observed_epoch":time.time(),"event_id":str(uuid.uuid4()),"value":2,"threshold":0}
            aid=db.execute("INSERT INTO alerts(monitor_id,severity,opening_evidence) VALUES(1,'warning',%s) RETURNING id",(psycopg.types.json.Jsonb(evidence),)).fetchone()["id"]
            self.run_id=enqueue(db,aid)
            self.job=db.execute("SELECT * FROM investigations WHERE id=%s",(self.run_id,)).fetchone()
        self.temp=tempfile.TemporaryDirectory()
        self.old_log=os.environ.get("OPENOPS_LOG_DIR")
        os.environ["OPENOPS_LOG_DIR"]=self.temp.name

    def connection(self):
        return psycopg.connect(row_factory=dict_row,options="-c search_path="+self.schema)

    def tearDown(self):
        if self.old_log is None:os.environ.pop("OPENOPS_LOG_DIR",None)
        else:os.environ["OPENOPS_LOG_DIR"]=self.old_log
        self.temp.cleanup()
        with psycopg.connect() as db:db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def source(self,tool,host,start,end,deadline):
        return [{"event_id":str(uuid.uuid4()),"observed_epoch":time.time(),**(
            {"voice_pending":"2","app_reachable":"true"} if tool=="timeline" else
            {"voice_output_enabled":"false","delivery_process":"active","sms_pending":"0"})}]

    def test_planned_tool_context_and_evaluator_are_actually_used(self):
        generator=FakeGenerator()
        with patch('receiver.investigation.evidence_query',side_effect=self.source) as tools:
            run(self.connection,self.job,generator)
        self.assertEqual([c.args[0] for c in tools.call_args_list],["timeline","portal_services"])
        self.assertEqual([c["role"] for c in generator.calls],["planner","investigator","evaluator"])
        with self.connection() as db:result=db.execute("SELECT * FROM investigations WHERE id=%s",(self.run_id,)).fetchone()
        self.assertEqual(result["status"],"completed")
        self.assertEqual(result["report"]["review"]["verdict"],"supported")
        self.assertTrue((Path(self.temp.name)/(self.run_id+".jsonl")).exists())

    def test_one_revision_and_final_critique_are_bounded(self):
        generator=FakeGenerator(revise=True)
        with patch('receiver.investigation.evidence_query',side_effect=self.source):run(self.connection,self.job,generator)
        self.assertEqual(len(generator.calls),5)
        self.assertEqual(generator.calls[-1]["role"],"final_evaluator")

    def test_empty_source_does_not_produce_a_model_report(self):
        generator=FakeGenerator()
        with patch('receiver.investigation.evidence_query',return_value=[]):
            with self.assertRaises(ValueError):run(self.connection,self.job,generator)
        self.assertEqual(generator.calls,[])

    def test_active_request_is_idempotent_and_completed_report_is_preserved(self):
        with self.connection() as db:
            self.assertEqual(enqueue(db,self.job['alert_id'],new_run=True),self.run_id)
            db.execute("UPDATE investigations SET status='completed',report=%s WHERE id=%s",(psycopg.types.json.Jsonb({'summary':'retained report'}),self.run_id))
        with self.connection() as db:
            new_id=enqueue(db,self.job['alert_id'],new_run=True)
            self.assertNotEqual(new_id,self.run_id)
            self.assertEqual(db.execute('SELECT report FROM investigations WHERE id=%s',(self.run_id,)).fetchone()['report']['summary'],'retained report')

    def test_manual_retry_limit_is_enforced(self):
        with self.connection() as db:db.execute("UPDATE investigations SET status='error',attempts=3 WHERE id=%s",(self.run_id,))
        with self.connection() as db:
            with self.assertRaises(ValueError):enqueue(db,self.job['alert_id'],retry=True)

    def test_provider_failure_does_not_generate_a_successful_report(self):
        generator=FakeGenerator()
        with patch('receiver.investigation.evidence_query',side_effect=self.source),patch.object(generator,'generate',side_effect=TimeoutError('provider timeout')) as call:
            with self.assertRaises(TimeoutError):run(self.connection,self.job,generator)
        self.assertEqual(call.call_count,1)
        with self.connection() as db:
            self.assertIsNone(db.execute('SELECT report FROM investigations WHERE id=%s',(self.run_id,)).fetchone()['report'])
            self.assertTrue(db.execute("SELECT 1 FROM investigation_trace WHERE run_id=%s AND action='model.failed'",(self.run_id,)).fetchone())
