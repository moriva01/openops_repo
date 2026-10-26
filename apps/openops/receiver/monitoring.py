"""Bounded deterministic monitoring; evidence is retrieved through Zetaris."""
from datetime import datetime, timezone
import math
import threading
import time
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

METRICS = {"voice_pending": "Voice output pending", "cpu_percent": "Host CPU utilization (%)",
           "memory_percent": "Host memory utilization (%)", "disk_percent": "Host disk utilization (%)"}
DDL = """
CREATE TABLE IF NOT EXISTS monitors(
 id serial PRIMARY KEY, name text NOT NULL, metric text NOT NULL, threshold double precision NOT NULL,
 duration_seconds integer NOT NULL, recovery_samples integer NOT NULL, severity text NOT NULL,
 enabled boolean NOT NULL DEFAULT true, state text NOT NULL DEFAULT 'normal',
 condition_since double precision, recovery_count integer NOT NULL DEFAULT 0,
 last_event_id text, last_observed double precision, last_evaluated timestamptz,
 last_value double precision, source_status text NOT NULL DEFAULT 'waiting', source_error text,
 revision integer NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS alerts(
 id bigserial PRIMARY KEY, monitor_id integer NOT NULL REFERENCES monitors(id),
 opened_at timestamptz NOT NULL DEFAULT clock_timestamp(), resolved_at timestamptz,
 acknowledged_at timestamptz, state text NOT NULL DEFAULT 'active', severity text NOT NULL,
 opening_evidence jsonb NOT NULL, resolution_evidence jsonb
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_alert ON alerts(monitor_id) WHERE resolved_at IS NULL;
CREATE TABLE IF NOT EXISTS alert_history(
 id bigserial PRIMARY KEY, monitor_id integer NOT NULL REFERENCES monitors(id), alert_id bigint REFERENCES alerts(id),
 happened_at timestamptz NOT NULL DEFAULT clock_timestamp(), action text NOT NULL, evidence jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS monitor_control(singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), last_query_at timestamptz, status text, detail text);
INSERT INTO monitor_control(singleton,status) VALUES(true,'waiting') ON CONFLICT DO NOTHING;
"""


def initialize(db):
    db.execute(DDL)
    if not db.execute("SELECT 1 FROM monitors LIMIT 1").fetchone():
        db.execute("""INSERT INTO monitors(name,metric,threshold,duration_seconds,recovery_samples,severity)
            VALUES('Voice output backlog','voice_pending',0,60,2,'warning')""")


def next_state(monitor, value, observed):
    """Pure transition. Call only once per distinct, fresh, ordered observation."""
    state = monitor["state"]
    since = monitor["condition_since"]
    count = monitor["recovery_count"]
    gap = monitor["last_observed"] is not None and observed - monitor["last_observed"] > 60
    if gap:
        since, count = None, 0
    if value > monitor["threshold"]:
        count = 0
        if state in ("firing", "recovering"):
            return "firing", None, 0, None
        since = observed if since is None else since
        if observed - since >= monitor["duration_seconds"]:
            return "firing", None, 0, "opened"
        return "pending", since, 0, None
    if state in ("firing", "recovering"):
        count += 1
        if count >= monitor["recovery_samples"]:
            return "normal", None, 0, "resolved"
        return "recovering", None, count, None
    return "normal", None, 0, None


def record(db, mid, aid, action, evidence):
    db.execute("INSERT INTO alert_history(monitor_id,alert_id,action,evidence) VALUES(%s,%s,%s,%s)",
               (mid, aid, action, Jsonb(evidence)))


def evaluate(db, row, now, source_error=None):
    monitors = db.execute("SELECT * FROM monitors WHERE enabled ORDER BY id FOR UPDATE").fetchall()
    for m in monitors:
        try:
            if source_error:
                raise ValueError(source_error)
            if row is None:
                raise ValueError("no_samples")
            observed = float(row["observed_epoch"])
            if not math.isfinite(observed) or now - observed > 60 or observed > now + 5:
                raise ValueError("stale_or_future_sample")
            if str(row.get("app_reachable", "")).lower() != "true" and m["metric"] == "voice_pending":
                raise ValueError("application_unreachable")
            value = float(row[m["metric"]])
            if not math.isfinite(value):
                raise ValueError("metric_unavailable")
        except (ValueError, TypeError, KeyError) as error:
            detail = str(error) if isinstance(error, ValueError) else "metric_unavailable"
            if m["source_status"] != "no_data":
                record(db, m["id"], None, "no_data", {"reason": detail, "source": "zetaris"})
            db.execute("""UPDATE monitors SET source_status='no_data', source_error=%s,
                condition_since=NULL,recovery_count=0,last_evaluated=clock_timestamp(),
                state=CASE WHEN state='pending' THEN 'normal' ELSE state END WHERE id=%s""", (detail, m["id"]))
            continue
        if m["last_event_id"] == row["event_id"] or (m["last_observed"] is not None and observed <= m["last_observed"]):
            db.execute("UPDATE monitors SET source_status='ok',source_error=NULL,last_evaluated=clock_timestamp() WHERE id=%s", (m["id"],))
            continue
        state, since, count, action = next_state(m, value, observed)
        evidence = {"source": "zetaris", "event_id": row["event_id"], "observed_epoch": observed,
                    "host_id": row["host_id"], "metric": m["metric"], "value": value,
                    "threshold": m["threshold"], "revision": m["revision"]}
        if action == "opened":
            aid = db.execute("""INSERT INTO alerts(monitor_id,severity,opening_evidence) VALUES(%s,%s,%s) RETURNING id""",
                             (m["id"], m["severity"], Jsonb(evidence))).fetchone()["id"]
            record(db, m["id"], aid, "opened", evidence)
        elif action == "resolved":
            result = db.execute("""UPDATE alerts SET state='resolved',resolved_at=clock_timestamp(),resolution_evidence=%s
                WHERE monitor_id=%s AND resolved_at IS NULL RETURNING id""", (Jsonb(evidence), m["id"])).fetchone()
            if result:
                record(db, m["id"], result["id"], "resolved", evidence)
        db.execute("""UPDATE monitors SET state=%s,condition_since=%s,recovery_count=%s,last_event_id=%s,
            last_observed=%s,last_value=%s,source_status='ok',source_error=NULL,last_evaluated=clock_timestamp() WHERE id=%s""",
            (state, since, count, row["event_id"], observed, value, m["id"]))


def configure(db, data):
    mid = int(data["id"])
    metric = data["metric"]
    threshold = float(data["threshold"])
    duration, recovery = int(data["duration_seconds"]), int(data["recovery_samples"])
    if metric not in METRICS or not math.isfinite(threshold) or threshold < 0:
        raise ValueError("Invalid metric or threshold")
    if not 0 <= duration <= 3600 or not 1 <= recovery <= 20 or type(data["enabled"]) is not bool:
        raise ValueError("Invalid duration, recovery count or enabled flag")
    name = str(data["name"]).strip()
    if not 1 <= len(name) <= 120 or data["severity"] not in ("warning", "critical"):
        raise ValueError("Invalid name or severity")
    current = db.execute("SELECT * FROM monitors WHERE id=%s FOR UPDATE", (mid,)).fetchone()
    if current is None:
        raise ValueError("Unknown monitor")
    if db.execute("SELECT 1 FROM alerts WHERE monitor_id=%s AND resolved_at IS NULL", (mid,)).fetchone():
        # Disable/re-enable without silently clearing or redefining an open incident.
        if any(current[k] != data[k] for k in ("metric", "threshold", "duration_seconds", "recovery_samples")):
            raise ValueError("Resolve the active alert before changing its condition; enablement can still change")
    db.execute("""UPDATE monitors SET name=%s,metric=%s,threshold=%s,duration_seconds=%s,recovery_samples=%s,
        severity=%s,enabled=%s,condition_since=NULL,recovery_count=0,revision=revision+1,
        state=CASE WHEN state='pending' THEN 'normal' ELSE state END WHERE id=%s""",
        (name,metric,threshold,duration,recovery,data["severity"],data["enabled"],mid))
    record(db,mid,None,"configured",{"enabled":data["enabled"],"metric":metric,"threshold":threshold,"duration_seconds":duration})


def acknowledge(db, aid):
    alert = db.execute("SELECT * FROM alerts WHERE id=%s FOR UPDATE", (aid,)).fetchone()
    if alert is None or alert["resolved_at"] is not None:
        raise ValueError("Alert is unknown or already resolved")
    if alert["acknowledged_at"] is None:
        db.execute("UPDATE alerts SET acknowledged_at=clock_timestamp() WHERE id=%s", (aid,))
        record(db, alert["monitor_id"], aid, "acknowledged", {"actor":"local_operator"})


def dashboard(db):
    monitors = db.execute("SELECT * FROM monitors ORDER BY id").fetchall()
    alerts = db.execute("SELECT a.*,m.name FROM alerts a JOIN monitors m ON m.id=a.monitor_id ORDER BY a.id DESC LIMIT 100").fetchall()
    history = db.execute("SELECT * FROM alert_history ORDER BY id DESC LIMIT 100").fetchall()
    samples = db.execute("""SELECT event_id, observed_epoch,cpu_percent,memory_percent,disk_percent,voice_pending,throughput
        FROM monitor_samples ORDER BY observed_epoch DESC LIMIT 120""").fetchall()
    return {"monitors":monitors,"alerts":alerts,"history":history,"samples":list(reversed(samples)),
            "source":db.execute("SELECT * FROM monitor_control WHERE singleton").fetchone(),"metrics":METRICS}


def loop(connection, logger):
    from receiver.zetaris import latest
    while True:
        start = time.monotonic()
        error = None
        try:
            row = latest()
        except Exception as exc:
            row, error = None, "zetaris_" + type(exc).__name__
        try:
            with connection() as db:
                db.row_factory = dict_row
                # One active evaluator, even if another process starts accidentally.
                if db.execute("SELECT pg_try_advisory_xact_lock(809601)").fetchone()["pg_try_advisory_xact_lock"]:
                    evaluate(db,row,time.time(),error)
                    db.execute("UPDATE monitor_control SET last_query_at=clock_timestamp(),status=%s,detail=%s WHERE singleton",
                               ("error" if error else "ok",error))
            logger("monitor.evaluated",source="zetaris",status="error" if error else "ok",error_type=error)
        except Exception as exc:
            logger("monitor.error",error_type=type(exc).__name__)
        time.sleep(max(1,15-(time.monotonic()-start)))
