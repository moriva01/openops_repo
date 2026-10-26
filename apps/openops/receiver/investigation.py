"""Durable, bounded incident investigation with read-only evidence tools."""
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import os

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from receiver.world_model import WorldStoreService,IngestPipelineService,ContextBuilderService
from receiver.nightshift import NightshiftGenerator
from receiver.zetaris import ADAPTER

DDL="""
CREATE TABLE IF NOT EXISTS investigations(
 id text PRIMARY KEY,alert_id bigint NOT NULL REFERENCES alerts(id),
 status text NOT NULL DEFAULT 'queued',attempts integer NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),started_at timestamptz,finished_at timestamptz,
 report jsonb,error_type text,manifest jsonb);
ALTER TABLE investigations DROP CONSTRAINT IF EXISTS investigations_alert_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS one_active_investigation ON investigations(alert_id) WHERE status IN ('queued','running');
CREATE TABLE IF NOT EXISTS investigation_trace(
 id bigserial PRIMARY KEY,run_id text NOT NULL REFERENCES investigations(id),
 happened_at timestamptz NOT NULL DEFAULT clock_timestamp(),action text NOT NULL,detail jsonb NOT NULL);
"""

TOOLS={
 "timeline":("voice_pending","oldest_pending_seconds","throughput","app_reachable"),
 "portal_services":("voice_output_enabled","sms_output_enabled","data_output_enabled","sms_pending","data_pending",
                    "api_process","mediation_process","delivery_process","app_reachable"),
 "host_resources":("cpu_percent","memory_percent","disk_percent"),
 "traffic":("voice_pending","sms_pending","data_pending","throughput","rejected_total")}
REPORT_CONTRACT={"status":"supported_hypothesis or insufficient_evidence","summary":"string",
 "hypotheses":[{"title":"string","explanation":"string","evidence_ids":["known evidence ID"],"confidence":"low/medium/high"}],
 "alternatives":[{"title":"string","explanation":"string","evidence_ids":["known evidence ID"],"confidence":"low/medium/high"}],
 "missing_evidence":["string"],"recommended_checks":["read-only check, never a claim of execution"]}


def initialize(db):
    db.execute(DDL)
    WorldStoreService(db).initialize()


def enqueue(db,alert_id,retry=False,new_run=False):
    if not db.execute("SELECT 1 FROM alerts WHERE id=%s FOR UPDATE",(alert_id,)).fetchone():
        raise ValueError("Unknown alert")
    row=db.execute("SELECT * FROM investigations WHERE alert_id=%s ORDER BY created_at DESC LIMIT 1 FOR UPDATE",(alert_id,)).fetchone()
    if row and row['status'] in ('queued','running'):return row['id']
    if row and not new_run:
        if retry and row["status"] in ("error","interrupted"):
            if row["attempts"]>=3:raise ValueError("Manual retry limit reached")
            db.execute("UPDATE investigations SET status='queued',error_type=NULL WHERE id=%s",(row["id"],))
        return row['id']
    if db.execute('SELECT count(*) n FROM investigations WHERE alert_id=%s',(alert_id,)).fetchone()['n']>=3:
        raise ValueError('Investigation limit reached for this alert')
    run_id="inv_"+uuid.uuid4().hex
    db.execute("INSERT INTO investigations(id,alert_id) VALUES(%s,%s)",(run_id,alert_id))
    return run_id


def trace(connection,run_id,action,detail):
    with connection() as db:
        db.execute("INSERT INTO investigation_trace(run_id,action,detail) VALUES(%s,%s,%s)",(run_id,action,Jsonb(detail)))
    entry={"timestamp":datetime.now(timezone.utc).isoformat(),"run_id":run_id,"action":action,"detail":detail}
    with (Path(os.environ.get("OPENOPS_LOG_DIR","/app/logs"))/(run_id+".jsonl")).open("a") as stream:
        stream.write(json.dumps(entry,allow_nan=False)+"\n")
    print(json.dumps({"action":action,"run_id":run_id}),flush=True)


def named_rows(reply):
    data=reply.get("records",reply.get("data"))
    if not isinstance(data,list):raise ValueError("Invalid Zetaris response")
    if not data:return []
    if isinstance(data[0],dict):return data
    headers=reply.get("headers")
    if not isinstance(headers,list):raise ValueError("Missing Zetaris column names")
    return [dict(zip(headers,row)) for row in data]


def evidence_query(tool,host_id,start,end,deadline):
    if tool not in TOOLS or time.monotonic()+25>deadline:raise TimeoutError("Evidence query budget")
    # Identifiers and column lists are fixed; the model never supplies SQL.
    host=host_id.replace("'","''")
    statement=("SELECT event_id,observed_epoch,"+",".join(TOOLS[tool])+" FROM openops_pg.monitor_samples "
               +"WHERE host_id='"+host+"' AND observed_epoch >= "+str(float(start))+" AND observed_epoch <= "+str(float(end))
               +" ORDER BY observed_epoch ASC LIMIT 30")
    return named_rows(ADAPTER.query(statement,30))


def validate_report(report,context):
    known={r["evidence_id"] for r in context["evidence"]}
    if report.get("status") not in ("supported_hypothesis","insufficient_evidence"):
        raise ValueError("Invalid report status")
    if not isinstance(report.get("summary"),str) or not 1<=len(report["summary"])<=3000:
        raise ValueError("Invalid report summary")
    for field in ("hypotheses","alternatives"):
        items=report.get(field)
        if not isinstance(items,list) or len(items)>5:raise ValueError("Invalid hypothesis list")
        for item in items:
            if not isinstance(item,dict) or any(not isinstance(item.get(k),str) or not 1<=len(item[k])<=2500 for k in ("title","explanation")):
                raise ValueError("Invalid hypothesis")
            refs=item.get("evidence_ids")
            if not isinstance(refs,list) or any(not isinstance(ref,str) or ref not in known for ref in refs):
                raise ValueError("Unknown evidence citation")
            if not refs:raise ValueError("Hypothesis must cite evidence; put untested ideas in missing_evidence")
            if item.get("confidence") not in ("low","medium","high"):raise ValueError("Invalid confidence")
    if report["status"]=="supported_hypothesis" and not report["hypotheses"]:
        raise ValueError("Supported status requires a cited hypothesis")
    for field in ("missing_evidence","recommended_checks"):
        if not isinstance(report.get(field),list) or len(report[field])>10 or any(not isinstance(v,str) or len(v)>1500 for v in report[field]):
            raise ValueError("Invalid recommendations")
    return report


def review_contract(review):
    if review.get("verdict") not in ("supported","insufficient","revise") or not isinstance(review.get("issues"),list):
        raise ValueError("Invalid evaluator response")
    if any(not isinstance(v,str) or len(v)>1500 for v in review["issues"]):raise ValueError("Invalid evaluator issues")
    return review


def run(connection,job,generator=None):
    run_id=job["id"]
    context_id=run_id+":attempt:"+str(job['attempts']+1)
    deadline=time.monotonic()+200
    generator=generator or NightshiftGenerator()
    def note(action,detail):trace(connection,run_id,action,detail)
    def model(role,payload):
        if len(generator.calls)>=5:raise ValueError("Model-call cap exceeded")
        note("model.started",{"role":role,"requested_model":os.environ.get("METERLESS_MODEL","meterless/auto")})
        try:result=generator.generate(role,payload,deadline)
        except Exception as error:
            note("model.failed",{"role":role,"error_type":type(error).__name__,"automatic_retry":False})
            raise
        if len(generator.calls)>5:raise ValueError("Model-call cap exceeded")
        note("model.completed",generator.calls[-1])
        note("model.output",{"role":role,"output":result})
        return result
    with connection() as db:
        db.row_factory=dict_row
        alert=db.execute("SELECT a.*,m.name,m.metric FROM alerts a JOIN monitors m ON m.id=a.monitor_id WHERE a.id=%s",(job["alert_id"],)).fetchone()
    if alert is None:raise ValueError("Alert no longer available")
    opening=alert["opening_evidence"]
    anchor=float(opening["observed_epoch"])
    host=opening["host_id"]
    start,end=anchor-120,min(time.time(),anchor+120)
    def fetch(tool):
        rows=evidence_query(tool,host,start,end,deadline)
        with connection() as db:
            db.row_factory=dict_row
            result=IngestPipelineService(WorldStoreService(db)).ingest(context_id,host,tool,rows)
        note("world.ingested",{"tool":tool,"rows":len(rows),**result})
    def context(budget=18000):
        with connection() as db:
            db.row_factory=dict_row
            result=ContextBuilderService(WorldStoreService(db)).build(context_id,anchor,budget=budget)
        note("world.context_built",{"evidence_count":len(result["evidence"]),"truncated":result["truncated"],"manifest":result["manifest"]})
        return result
    fetch("timeline")
    initial=context(budget=4000)
    if not initial["evidence"]:raise ValueError("No source evidence in incident window")
    objective={"monitor_metric":alert["metric"],"observed_value":opening["value"],"threshold":opening["threshold"],
               "question":"What explains the sustained violation? Distinguish symptoms, service/process state and configuration; consider alternative explanations.",
               "application_flow":"Input portals -> mediation worker -> enabled output portals -> durable outbox. A healthy process can coexist with a disabled portal. A backlog may reflect portal configuration, process failure or resource contention; do not infer those states from queue size alone.",
               "incident_window":{"start_epoch":start,"end_epoch":end},"automatic_remediation":False}
    plan=model("planner",{"contract":{"tools":["portal_services"],"reason":"Explain which evidence gap the selected tools address"},
         "instruction":"Choose zero, one or two distinct allowed tool names based on this incident. The contract is a shape example, not a prescribed choice.",
         "allowed_tools":{k:list(v) for k,v in TOOLS.items() if k!="timeline"},"objective":objective,"context":initial})
    selected=plan.get("tools")
    if not isinstance(selected,list) or len(selected)>2 or len(set(selected))!=len(selected) or any(t not in TOOLS or t=="timeline" for t in selected):
        raise ValueError("Planner chose invalid tools")
    note("planner.selected_tools",{"tools":selected,"reason":str(plan.get("reason",""))[:1000]})
    requested_tools=list(selected)
    # A symptom-only query cannot support an explanation. This explicit evidence
    # policy adds the relevant state source; the model still chooses supplemental tools.
    required="portal_services" if alert["metric"]=="voice_pending" else "host_resources"
    if required not in selected:
        selected=selected[:1]+[required]
        note("policy.required_evidence_tool",{"tool":required,"model_requested":requested_tools,
              "executed_tools":selected,"reason":"Verify configuration/process or host state rather than only restating a symptom"})
    for tool in selected:fetch(tool)
    grounded=context()
    report=model("investigator",{"contract":REPORT_CONTRACT,"objective":objective,"context":grounded})
    guard=[]
    try:validate_report(report,grounded)
    except ValueError as error:guard=[str(error)]
    critique_payload={"contract":{"verdict":"supported/insufficient/revise","issues":["specific unsupported claims, contradictions, uncertainty or citation problems"]},
        "instruction":"Independently inspect every factual claim against cited evidence. A citation existing is not proof it supports the claim. Never mark an unobserved causal claim as established. Demand uncertainty if evidence is missing.",
        "objective":objective,"context":grounded,"report":report,"structural_issues":guard}
    review=review_contract(model("evaluator",critique_payload))
    if guard or review["verdict"]=="revise":
        note("report.revision_requested",{"issues":guard+review["issues"]})
        report=model("investigator_revision",{"contract":REPORT_CONTRACT,"objective":objective,"context":grounded,
                     "previous_report":report,"required_corrections":guard+review["issues"]})
        validate_report(report,grounded)
        critique_payload.update(report=report,structural_issues=[])
        review=review_contract(model("final_evaluator",critique_payload))
    else:validate_report(report,grounded)
    report["review"]=review
    report["evidence"]=grounded["evidence"]
    report["scope"]={"historical_incident_window":True,"start_epoch":start,"end_epoch":end,"remediation_executed":False}
    manifest={**grounded["manifest"],"world_context_key":context_id,"model_calls":generator.calls,
              "planner_requested_tools":requested_tools,"required_evidence_tool":required,"evidence_tools":["timeline"]+selected,
              "max_model_calls":5,"max_tool_queries":3,"deadline_seconds":200,"source":"zetaris","provider":"meterless_nightshift"}
    status="needs_review" if review["verdict"]=="revise" else "completed"
    if review["verdict"]=="insufficient":report["status"]="insufficient_evidence"
    with connection() as db:
        db.execute("UPDATE investigations SET status=%s,report=%s,manifest=%s,finished_at=clock_timestamp() WHERE id=%s",
                   (status,Jsonb(report),Jsonb(manifest),run_id))
    note("investigation.finished",{"status":status,"verdict":review["verdict"],"model_calls":len(generator.calls)})


def loop(connection,logger):
    while True:
        job=None
        try:
            with connection() as db:
                db.row_factory=dict_row
                db.execute("""UPDATE investigations SET status='interrupted',error_type='WorkerInterrupted',finished_at=clock_timestamp()
                    WHERE status='running' AND started_at<clock_timestamp()-interval '5 minutes'""")
                for alert in db.execute("SELECT id FROM alerts WHERE resolved_at IS NULL AND opened_at>clock_timestamp()-interval '10 minutes'").fetchall():
                    enqueue(db,alert["id"])
                job=db.execute("SELECT * FROM investigations WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
                if job:
                    db.execute("UPDATE investigations SET status='running',attempts=attempts+1,started_at=clock_timestamp() WHERE id=%s",(job["id"],))
            if job:
                trace(connection,job["id"],"investigation.started",{"alert_id":job["alert_id"],"attempt":job["attempts"]+1})
                run(connection,job)
        except Exception as error:
            logger("investigation.error",error_type=type(error).__name__)
            if job:
                with connection() as db:
                    db.execute("UPDATE investigations SET status='error',error_type=%s,finished_at=clock_timestamp() WHERE id=%s",(type(error).__name__,job["id"]))
                trace(connection,job["id"],"investigation.failed",{"error_type":type(error).__name__,"automatic_retry":False})
        time.sleep(3)
