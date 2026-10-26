"""Minimal Meterless World Model reference architecture, with PostgreSQL live storage and SQLite offline storage.

Implements durable entities, immutable observations, typed relationships, ordered
idempotent ingest and a structured bounded context actually consumed by agents.
Advanced enrichment, vector memory and autonomous repair are not implemented.
"""
import hashlib
import json
import math
import sqlite3

DDL="""
CREATE TABLE IF NOT EXISTS wm_schema(version integer PRIMARY KEY);
INSERT INTO wm_schema VALUES(1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS wm_entities(id text PRIMARY KEY,kind text NOT NULL,anchor jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS wm_contexts(id text PRIMARY KEY,run_id text NOT NULL,properties jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS wm_observations(
 id text PRIMARY KEY,entity_id text NOT NULL REFERENCES wm_entities(id),source_event text NOT NULL,
 observed_epoch double precision NOT NULL,tool text NOT NULL,facts jsonb NOT NULL);
CREATE INDEX IF NOT EXISTS wm_entity_time ON wm_observations(entity_id,observed_epoch);
CREATE TABLE IF NOT EXISTS wm_memberships(
 context_id text REFERENCES wm_contexts(id),observation_id text REFERENCES wm_observations(id),
 PRIMARY KEY(context_id,observation_id));
CREATE TABLE IF NOT EXISTS wm_edges(
 id text PRIMARY KEY,source_id text REFERENCES wm_entities(id),target_id text REFERENCES wm_entities(id),
 relation text NOT NULL,provenance jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS wm_ingest_jobs(
 id text PRIMARY KEY,context_id text NOT NULL,status text NOT NULL,stages jsonb NOT NULL);
"""


def stable_id(kind,*parts):
    raw=json.dumps(parts,sort_keys=True,separators=(",",":"))
    return kind+"_"+hashlib.sha256(raw.encode()).hexdigest()[:24]


def scalar(value):
    if value is None or value in ("null","None",""):
        return None
    if isinstance(value,str) and value.lower() in ("true","false"):
        return value.lower()=="true"
    try:
        if isinstance(value,bool):return value
        number=float(value)
        return number if math.isfinite(number) else None
    except (TypeError,ValueError):
        return str(value)[:120]


class WorldStoreService:
    def __init__(self,db):self.db=db
    @classmethod
    def sqlite(cls,path=':memory:'):
        db=sqlite3.connect(path,timeout=5)
        db.execute('PRAGMA foreign_keys=ON')
        def row_factory(cursor,row):
            result=dict(zip((column[0] for column in cursor.description),row))
            for key in ('anchor','properties','facts','provenance','stages'):
                if key in result and isinstance(result[key],str):result[key]=json.loads(result[key])
            return result
        db.row_factory=row_factory
        return cls(db)

    def initialize(self):
        if isinstance(self.db,sqlite3.Connection):self.db.executescript(DDL)
        else:self.db.execute(DDL)

    def execute(self,statement,parameters=()):
        if isinstance(self.db,sqlite3.Connection):statement=statement.replace('%s','?')
        return self.db.execute(statement,parameters)

    def json(self,value):
        if isinstance(self.db,sqlite3.Connection):return json.dumps(value,allow_nan=False)
        from psycopg.types.json import Jsonb
        return Jsonb(value)


class IngestPipelineService:
    STAGES=("reconcile","classify","persist_context","measure","derive","persist_edges",
            "rebuild_views","annotate_sources","rebuild_aggregates","mark_stale")

    def __init__(self,store):self.db=store.db;self.store=store

    def ingest(self,run_id,host_identity,tool,rows):
        store=self.store
        context=stable_id("context",run_id)
        host=stable_id("entity","host",host_identity)
        app=stable_id("entity","application",host_identity,"telemediation")
        portal=stable_id("entity","portal",host_identity,"voice")
        for eid,kind,label in ((host,"host","Monitored server"),(app,"application","TeleMediation Convergent"),(portal,"portal","VOICE output")):
            store.execute("INSERT INTO wm_entities VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                       (eid,kind,store.json({"label":label,"identity_anchor":eid})))
        store.execute("INSERT INTO wm_contexts VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                   (context,run_id,store.json({"intent":"incident_investigation","agent_id":"evidence_researcher","schema":1})))
        job=stable_id("ingest",context,tool,[r["event_id"] for r in rows])
        observations=[]
        for row in rows:
            facts={k:scalar(v) for k,v in row.items() if k not in ("host_id","hostname","event_id","observed_epoch")}
            oid=stable_id("observation",row["event_id"],tool,facts)
            target=host if tool=="host_resources" else portal if tool=="timeline" else app
            store.execute("INSERT INTO wm_observations VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (oid,target,row["event_id"],float(row["observed_epoch"]),tool,store.json(facts)))
            store.execute("INSERT INTO wm_memberships VALUES(%s,%s) ON CONFLICT DO NOTHING",(context,oid))
            observations.append(oid)
        for source,target,relation in ((app,host,"runs_on"),(portal,app,"part_of")):
            store.execute("INSERT INTO wm_edges VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (stable_id("edge",source,target,relation),source,target,relation,store.json({"source":"application_topology","schema":1})))
        # All writes commit together. A failed ingest has no partially advanced job.
        # Canonical counts/latest views are derived from immutable records on read.
        stages={"reconcile":"stable IDs preserve existing memberships",
                "classify":"map source tool to typed host/application/portal entity",
                "persist_context":"durable attributed incident context",
                "measure":"normalize typed observed facts; no generated scores",
                "derive":"declared application topology only; no inferred causal edges",
                "persist_edges":"idempotent typed topology links",
                "rebuild_views":"derived on context read",
                "annotate_sources":"context memberships; raw source rows unchanged",
                "rebuild_aggregates":"derived from immutable records on read",
                "mark_stale":"bounded historical selection; no global maintenance job"}
        store.execute("INSERT INTO wm_ingest_jobs VALUES(%s,%s,'completed',%s) ON CONFLICT DO NOTHING",(job,context,store.json(stages)))
        return {"context_id":context,"job_id":job,"observation_ids":observations,"stages":stages}


class ContextBuilderService:
    def __init__(self,store):self.db=store.db;self.store=store

    def build(self,run_id,anchor_epoch,budget=24000):
        context=stable_id("context",run_id)
        rows=self.store.execute("""SELECT o.* FROM wm_observations o JOIN wm_memberships m ON m.observation_id=o.id
            WHERE m.context_id=%s ORDER BY abs(o.observed_epoch-%s),o.id LIMIT 80""",(context,anchor_epoch)).fetchall()
        items=[]
        for row in rows:
            item={"evidence_id":row["id"],"source_event_id":row["source_event"],"observed_epoch":row["observed_epoch"],
                  "tool":row["tool"],"facts":row["facts"],"selectionReason":"same incident context; nearest opening observation"}
            if len(json.dumps(items+[item]))>budget:break
            items.append(item)
        entity_ids={r["entity_id"] for r in rows if r["id"] in {i["evidence_id"] for i in items}}
        ids=sorted(entity_ids)
        marks=','.join('%s' for _ in ids)
        entities=[dict(r) for r in self.store.execute("SELECT * FROM wm_entities WHERE id IN ("+marks+") ORDER BY id",ids)] if ids else []
        edges=[dict(r) for r in self.store.execute("SELECT * FROM wm_edges WHERE source_id IN ("+marks+") AND target_id IN ("+marks+") ORDER BY id",ids+ids)] if ids else []
        return {"schema":"openops.world_context.v1","intent":"investigate_alert","strategy":"incident-window/anchor-priority",
                "entities":entities,"relationships":edges,"evidence":items,"truncated":len(items)<len(rows),
                "manifest":{"implemented":["WorldStoreService","IngestPipelineService","ContextBuilderService","stable_ids","atomic_ingest","provenance","derived_context"],
                            "not_implemented":["vector_memory","autonomous_repair","enrichment_queue","world_migrations"],
                            "context_consumed_by":["planner","investigator","evaluator"],"schema_version":1}}
