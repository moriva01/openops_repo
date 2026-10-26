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
from receiver.investigation_engine import TOOLS,REPORT_CONTRACT,validate_report,review_contract,execute
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


def run(connection,job,generator=None):
    run_id=job['id']
    with connection() as db:
        db.row_factory=dict_row
        alert=db.execute("SELECT a.*,m.name,m.metric FROM alerts a JOIN monitors m ON m.id=a.monitor_id WHERE a.id=%s",(job['alert_id'],)).fetchone()
    if alert is None:raise ValueError('Alert no longer available')
    def ingest(context_id,host,tool,rows):
        with connection() as db:
            db.row_factory=dict_row
            return IngestPipelineService(WorldStoreService(db)).ingest(context_id,host,tool,rows)
    def context(context_id,anchor,budget):
        with connection() as db:
            db.row_factory=dict_row
            return ContextBuilderService(WorldStoreService(db)).build(context_id,anchor,budget=budget)
    result=execute(alert,run_id,job['attempts']+1,generator or NightshiftGenerator(),evidence_query,ingest,context,
                   lambda action,detail:trace(connection,run_id,action,detail),requested_model=os.environ.get('METERLESS_MODEL','meterless/auto'))
    with connection() as db:
        db.execute("UPDATE investigations SET status=%s,report=%s,manifest=%s,finished_at=clock_timestamp() WHERE id=%s",
                   (result['status'],Jsonb(result['report']),Jsonb(result['manifest']),run_id))
    trace(connection,run_id,'investigation.finished',{'status':result['status'],'verdict':result['report']['review']['verdict'],
                                                    'model_calls':len(result['manifest']['model_calls'])})


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
