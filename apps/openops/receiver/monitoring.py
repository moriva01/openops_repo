"""Bounded deterministic monitoring; evidence is retrieved through Zetaris."""
from datetime import datetime, timezone
import math
import threading
import time
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

METRICS = {"voice_pending": "Voice output pending", "cpu_percent": "Host CPU utilization (%)",
           "memory_percent": "Host memory utilization (%)", "disk_percent": "Host disk utilization (%)", "sms_pending":"SMS output pending", "data_pending":"Data output pending",
 "oldest_pending_seconds":"Oldest pending age (seconds)", "app_down":"Application unavailable (1 = down)",
 "api_down":"API process unavailable (1 = down)","mediation_down":"Mediation process unavailable (1 = down)","delivery_down":"Delivery process unavailable (1 = down)"}
SEVERITIES = ['info','warning','minor','major','critical']
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
    db.execute("""ALTER TABLE monitors ADD COLUMN IF NOT EXISTS host_id text;
      ALTER TABLE monitors ADD COLUMN IF NOT EXISTS deleted boolean NOT NULL DEFAULT false;
      ALTER TABLE monitors ADD COLUMN IF NOT EXISTS thresholds jsonb NOT NULL DEFAULT '[]';
      ALTER TABLE monitors ADD COLUMN IF NOT EXISTS comparator text NOT NULL DEFAULT 'above';
      ALTER TABLE alerts ADD COLUMN IF NOT EXISTS acknowledged_by text;
      ALTER TABLE alerts ADD COLUMN IF NOT EXISTS ticket_server_id integer;
      ALTER TABLE alerts ADD COLUMN IF NOT EXISTS ticket_ref text;
      ALTER TABLE alerts ADD COLUMN IF NOT EXISTS ticket_url text;""")
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
    row=db.execute("INSERT INTO alert_history(monitor_id,alert_id,action,evidence) VALUES(%s,%s,%s,%s) RETURNING id",(mid,aid,action,Jsonb(evidence))).fetchone()
    if aid:
        from receiver.notifications import enqueue
        enqueue(db,row['id'],aid,action,evidence)


def severity_for(m,value):
    levels=m.get('thresholds') or [{'severity':m['severity'],'value':m['threshold']}]
    crossed=[v['severity'] for v in levels if (value>v['value'] if m.get('comparator','above')=='above' else value<v['value'])]
    return max(crossed,key=SEVERITIES.index) if crossed else None


def evaluate(db, row, now, source_error=None, host_id=None):
    monitors = db.execute("SELECT * FROM monitors WHERE enabled AND NOT deleted AND (%s::text IS NULL OR host_id=%s) ORDER BY id FOR UPDATE",(host_id,host_id)).fetchall()
    for m in monitors:
        if host_id is None and row and m.get('host_id') and row.get('host_id')!=m['host_id']:continue
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
            if m['metric']=='app_down':
                if row.get('app_reachable') is None:raise ValueError('metric_unavailable')
                value=0.0 if str(row['app_reachable']).lower()=='true' else 1.0
            elif m['metric'] in ('api_down','mediation_down','delivery_down'):
                process=row.get(m['metric'].replace('_down','_process'))
                if process is None:raise ValueError('metric_unavailable')
                value=0.0 if process=='active' else 1.0
            else:value = float(row[m["metric"]])
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
        current_severity=severity_for(m,value)
        transition=dict(m,threshold=0)
        state, since, count, action = next_state(transition,1 if current_severity else 0,observed)
        evidence = {"source": "zetaris", "event_id": row["event_id"], "observed_epoch": observed,
                    "host_id": row["host_id"], "metric": m["metric"], "value": value,
                    "threshold": m["threshold"], "thresholds":m.get("thresholds",[]),"comparator":m.get("comparator","above"), "revision": m["revision"]}
        if action == "opened":
            aid = db.execute("""INSERT INTO alerts(monitor_id,severity,opening_evidence) VALUES(%s,%s,%s) RETURNING id""",
                             (m["id"], current_severity, Jsonb(evidence))).fetchone()["id"]
            record(db, m["id"], aid, "opened", evidence)
        elif action == "resolved":
            result = db.execute("""UPDATE alerts SET state='resolved',resolved_at=clock_timestamp(),resolution_evidence=%s
                WHERE monitor_id=%s AND resolved_at IS NULL RETURNING id""", (Jsonb(evidence), m["id"])).fetchone()
            if result:
                record(db, m["id"], result["id"], "resolved", evidence)
        if current_severity and action!='opened':
            changed=db.execute("UPDATE alerts SET severity=%s WHERE monitor_id=%s AND resolved_at IS NULL AND severity<>%s RETURNING id",(current_severity,m['id'],current_severity)).fetchone()
            if changed:record(db,m['id'],changed['id'],'severity_changed',{**evidence,'severity':current_severity})
        db.execute("""UPDATE monitors SET state=%s,condition_since=%s,recovery_count=%s,last_event_id=%s,
            last_observed=%s,last_value=%s,source_status='ok',source_error=NULL,last_evaluated=clock_timestamp() WHERE id=%s""",
            (state, since, count, row["event_id"], observed, value, m["id"]))


def configure(db, data, actor='system'):
    mid=int(data.get('id') or 0)
    current=db.execute("SELECT * FROM monitors WHERE id=%s AND NOT deleted FOR UPDATE",(mid,)).fetchone() if mid else None
    if mid and not current:raise ValueError('Unknown monitor')
    if data.get('action')=='delete':
        if db.execute('SELECT 1 FROM alerts WHERE monitor_id=%s AND resolved_at IS NULL',(mid,)).fetchone():raise ValueError('Resolve the active alert before deleting its monitor')
        db.execute('UPDATE monitors SET deleted=true,enabled=false WHERE id=%s',(mid,));record(db,mid,None,'deleted',{'actor':actor});return mid
    metric=data['metric'];name=str(data['name']).strip();duration=int(data['duration_seconds']);recovery=int(data['recovery_samples'])
    levels=data.get('thresholds')
    comparator=data.get('comparator','above')
    if not levels:levels=[{'severity':data['severity'],'value':float(data['threshold'])}]
    if not isinstance(levels,list) or not 1<=len(levels)<=len(SEVERITIES):raise ValueError('Provide one or more severity thresholds')
    normalized=[]
    for level in levels:
        value=float(level['value']);severity=level['severity']
        if severity not in SEVERITIES or not math.isfinite(value) or value<0:raise ValueError('Invalid severity threshold')
        normalized.append({'severity':severity,'value':value})
    normalized.sort(key=lambda v:SEVERITIES.index(v['severity']))
    if len({v['severity'] for v in normalized})!=len(normalized):raise ValueError('Duplicate severity')
    values=[v['value'] for v in normalized]
    if any((a>=b if comparator=='above' else a<=b) for a,b in zip(values,values[1:])):raise ValueError('Thresholds must increase with severity for above, decrease for below')
    threshold=normalized[0]['value'];severity=normalized[0]['severity']
    if metric not in METRICS or not 1<=len(name)<=120 or comparator not in ('above','below'):raise ValueError('Invalid monitor settings')
    if not 0<=duration<=3600 or not 1<=recovery<=20 or type(data['enabled']) is not bool:raise ValueError('Invalid duration, recovery count or enabled flag')
    host=data.get('host_id',current['host_id'] if current else None)
    if host and not db.execute('SELECT 1 FROM managed_hosts WHERE id=%s AND enabled',(host,)).fetchone():raise ValueError('Select an enabled registered host')
    if not current and not host:raise ValueError('Select a host')
    if current:
        if db.execute('SELECT 1 FROM alerts WHERE monitor_id=%s AND resolved_at IS NULL',(mid,)).fetchone():
            oldlevels=current['thresholds'] or [{'severity':current['severity'],'value':current['threshold']}]
            if any((metric!=current['metric'],host!=current['host_id'],duration!=current['duration_seconds'],recovery!=current['recovery_samples'],normalized!=oldlevels,comparator!=current['comparator'])):raise ValueError('Resolve active alert before changing its condition')
        db.execute("""UPDATE monitors SET name=%s,host_id=%s,metric=%s,threshold=%s,thresholds=%s,comparator=%s,duration_seconds=%s,
          recovery_samples=%s,severity=%s,enabled=%s,condition_since=NULL,recovery_count=0,revision=revision+1,
          state=CASE WHEN state='pending' THEN 'normal' ELSE state END WHERE id=%s""",
          (name,host,metric,threshold,Jsonb(normalized),comparator,duration,recovery,severity,data['enabled'],mid))
    else:
        mid=db.execute("""INSERT INTO monitors(name,host_id,metric,threshold,thresholds,comparator,duration_seconds,recovery_samples,severity,enabled)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",(name,host,metric,threshold,Jsonb(normalized),comparator,duration,recovery,severity,data['enabled'])).fetchone()['id']
    record(db,mid,None,'configured',{'actor':actor,'enabled':data['enabled'],'metric':metric,'thresholds':normalized,'host_id':host})
    return mid


def acknowledge(db, aid, data=None, actor='local_operator'):
    data=data or {}
    alert=db.execute('SELECT * FROM alerts WHERE id=%s FOR UPDATE',(aid,)).fetchone()
    if alert is None or alert['resolved_at'] is not None:raise ValueError('Alert is unknown or already resolved')
    ack=data.get('acknowledged',True)
    if type(ack) is not bool:raise ValueError('Invalid acknowledgement')
    server=data.get('ticket_server_id');ref=str(data.get('ticket_ref','')).strip();link=None
    if len(ref)>120 or (ref and not server) or (server and not ref):raise ValueError('Select ticket server and enter ticket reference')
    if server:
        ticket=db.execute('SELECT * FROM ticket_servers WHERE id=%s AND enabled',(int(server),)).fetchone()
        if not ticket:raise ValueError('Unknown ticket server')
        from urllib.parse import quote
        link=ticket['url'].rstrip('/')+'/'+quote(ref,safe='')
    db.execute("""UPDATE alerts SET acknowledged_at=CASE WHEN %s THEN coalesce(acknowledged_at,clock_timestamp()) ELSE NULL END,
        acknowledged_by=%s,ticket_server_id=%s,ticket_ref=%s,ticket_url=%s WHERE id=%s""",
        (ack,actor if ack else None,int(server) if server else None,ref or None,link,aid))
    record(db,alert['monitor_id'],aid,'acknowledged' if ack else 'unacknowledged',{'actor':actor,'ticket_ref':ref,'ticket_server_id':server})


def dashboard(db,host=None):
    monitors=db.execute("SELECT m.*,h.name host_name FROM monitors m LEFT JOIN managed_hosts h ON h.id=m.host_id WHERE NOT m.deleted AND (%s::text IS NULL OR m.host_id=%s) ORDER BY m.id",(host,host)).fetchall()
    alerts=db.execute("""SELECT a.*,m.name,m.host_id,m.metric,m.last_value,m.comparator,h.name host_name FROM alerts a JOIN monitors m ON m.id=a.monitor_id
      LEFT JOIN managed_hosts h ON h.id=m.host_id WHERE (%s::text IS NULL OR m.host_id=%s) ORDER BY a.id DESC LIMIT 200""",(host,host)).fetchall()
    history=db.execute("SELECT a.* FROM alert_history a JOIN monitors m ON m.id=a.monitor_id WHERE (%s::text IS NULL OR m.host_id=%s) ORDER BY a.id DESC LIMIT 200",(host,host)).fetchall()
    samples=db.execute("""SELECT * FROM (SELECT s.*,row_number() OVER(PARTITION BY host_id ORDER BY observed_epoch DESC) rank
      FROM monitor_samples s WHERE (%s::text IS NULL OR host_id=%s)) recent WHERE rank<=120 ORDER BY observed_epoch DESC LIMIT 6000""",(host,host)).fetchall()
    hosts=db.execute("""SELECT h.id,h.name,h.address,h.client_id,h.enabled,c.name client_name,
      extract(epoch FROM max(t.observed_at)) latest_epoch FROM managed_hosts h LEFT JOIN clients c ON c.id=h.client_id
      LEFT JOIN telemetry_events t ON t.host_id=h.id GROUP BY h.id,c.name ORDER BY h.name""").fetchall()
    latest=db.execute("""SELECT DISTINCT ON(host_id) host_id,observed_at,payload FROM telemetry_events
      WHERE (%s::text IS NULL OR host_id=%s) ORDER BY host_id,observed_at DESC""",(host,host)).fetchall()
    return {'monitors':monitors,'alerts':alerts,'history':history,'samples':list(reversed(samples)),
      'hosts':hosts,'latest':latest,'source':db.execute('SELECT * FROM monitor_control WHERE singleton').fetchone(),
      'metrics':METRICS,'severities':SEVERITIES,'ticket_servers':db.execute('SELECT * FROM ticket_servers WHERE enabled ORDER BY name').fetchall(),
      'activity':db.execute('SELECT * FROM system_activity ORDER BY id DESC LIMIT 200').fetchall(),
      'deliveries':db.execute('SELECT id,connector_name,status,attempts,last_error,created_at,finished_at FROM notification_deliveries ORDER BY id DESC LIMIT 50').fetchall()}


def loop(connection, logger):
    from receiver.zetaris import latest_hosts
    while True:
        start = time.monotonic()
        error = None
        try:
            rows = latest_hosts()
        except Exception as exc:
            rows, error = [], "zetaris_" + type(exc).__name__
        try:
            with connection() as db:
                db.row_factory = dict_row
                # One active evaluator, even if another process starts accidentally.
                if db.execute("SELECT pg_try_advisory_xact_lock(809601)").fetchone()["pg_try_advisory_xact_lock"]:
                    hosts=db.execute('SELECT id FROM managed_hosts WHERE enabled').fetchall()
                    by_host={r['host_id']:r for r in rows}
                    for host in hosts:evaluate(db,by_host.get(host['id']),time.time(),error,host_id=host['id'])
                    db.execute("UPDATE monitor_control SET last_query_at=clock_timestamp(),status=%s,detail=%s WHERE singleton",
                               ("error" if error else "ok",error))
            logger("monitor.evaluated",source="zetaris",status="error" if error else "ok",error_type=error)
        except Exception as exc:
            logger("monitor.error",error_type=type(exc).__name__)
        time.sleep(max(1,15-(time.monotonic()-start)))
