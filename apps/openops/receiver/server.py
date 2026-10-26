import hmac
import json
import math
import os
from pathlib import Path
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
import uuid

import psycopg
from psycopg.types.json import Jsonb
from psycopg.rows import dict_row
from receiver import monitoring, investigation, access, notifications
from http.cookies import SimpleCookie

LOCK = threading.Lock()
SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry_events (
  event_id uuid PRIMARY KEY,
  host_id text NOT NULL,
  hostname text NOT NULL,
  observed_at timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  payload jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS telemetry_host_time ON telemetry_events(host_id,observed_at DESC);
CREATE TABLE IF NOT EXISTS receiver_schema(version integer PRIMARY KEY);
INSERT INTO receiver_schema VALUES(1) ON CONFLICT DO NOTHING;
"""


def connection():
    return psycopg.connect(connect_timeout=3, options=os.environ.get("PGOPTIONS", "-c statement_timeout=4000"))


def initialize():
    with connection() as db:
        db.execute(SCHEMA)
        monitoring.initialize(db)
        investigation.initialize(db)
        access.initialize(db)
        notifications.initialize(db)
        db.execute("UPDATE monitors SET host_id=%s WHERE host_id IS NULL",(os.environ.get('OPENOPS_HOST_ID','tmc-lab-01'),))


def log(action, **fields):
    entry = json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "action": action, **fields})
    with LOCK:
        print(entry, flush=True)
        with (Path(os.environ.get("OPENOPS_LOG_DIR", "/app/logs")) / "receiver.jsonl").open("a") as stream:
            stream.write(entry + "\n")


class EventConflict(Exception):
    pass


def validate(batch, allowed_host=None):
    if not isinstance(batch, dict) or batch.get("schema") != "openops.batch.v1":
        raise ValueError("Expected openops.batch.v1")
    events = batch.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 50:
        raise ValueError("Batch must contain 1..50 events")
    ids = set()
    for item in events:
        if not isinstance(item, dict) or item.get("schema") != "openops.telemetry.v1":
            raise ValueError("Expected openops.telemetry.v1 event")
        event_id = str(uuid.UUID(item.get("event_id", "")))
        if item["event_id"] != event_id or event_id in ids:
            raise ValueError("Event IDs must be unique canonical UUIDs within a batch")
        ids.add(event_id)
        if item.get("host_id") != (allowed_host or os.environ["OPENOPS_HOST_ID"]):
            raise ValueError("Host is not registered for this credential")
        if not isinstance(item.get("hostname"), str) or not 1 <= len(item["hostname"]) <= 253:
            raise ValueError("Invalid hostname")
        stamp = datetime.fromisoformat(item.get("observed_at", "").replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            raise ValueError("Timestamp requires timezone")
        if (stamp - datetime.now(timezone.utc)).total_seconds() > 300:
            raise ValueError("Timestamp more than five minutes in the future")
        for key in ("host", "application", "systemd_units"):
            if not isinstance(item.get(key), dict):
                raise ValueError(key + " must be an object")
        if not isinstance(item.get("collection_errors"), list):
            raise ValueError("collection_errors must be an array")
        # Traverse numbers to reject non-finite metrics even outside known fields.
        def check(value):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Non-finite metric")
            if isinstance(value, dict):
                for v in value.values():
                    check(v)
            elif isinstance(value, list):
                for v in value:
                    check(v)
        check(item)
    return events


def persist(events):
    accepted, inserted = [], 0
    # Acknowledgement is produced only after the transaction context commits.
    with connection() as db:
        for item in events:
            row = db.execute("""INSERT INTO telemetry_events(event_id,host_id,hostname,observed_at,payload)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(event_id) DO NOTHING RETURNING event_id""",
                (item["event_id"], item["host_id"], item["hostname"], item["observed_at"], Jsonb(item))).fetchone()
            if row:
                inserted += 1
            else:
                stored = db.execute("SELECT payload FROM telemetry_events WHERE event_id=%s", (item["event_id"],)).fetchone()[0]
                if stored != item:
                    raise EventConflict("Event ID already stored with different content")
            accepted.append(item["event_id"])
    return {"accepted_event_ids": accepted, "inserted": inserted, "duplicates": len(accepted) - inserted}


class Handler(BaseHTTPRequestHandler):
    server_version='OpenOps/0.2'
    def setup(self):
        super().setup();self.connection.settimeout(15)
    def log_message(self,*_):pass
    def reply(self,code,body,cookie=None):
        raw=json.dumps(body,default=str,allow_nan=False).encode()
        self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(raw)
    def bearer(self):
        header=self.headers.get('Authorization','')
        return header[7:] if header.startswith('Bearer ') else None
    def session(self):
        try:
            cookie=SimpleCookie(self.headers.get('Cookie',''));return cookie['openops_session'].value if 'openops_session' in cookie else None
        except Exception:return None
    def identity(self,db):return access.principal(db,self.bearer(),self.session())
    def read_body(self,max_size=65536):
        size=int(self.headers.get('Content-Length','0'))
        if not 0<size<=max_size:raise ValueError('Invalid request size')
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON content type required')
        body=json.loads(self.rfile.read(size))
        if not isinstance(body,dict):raise ValueError('JSON object required')
        return body
    def do_POST(self):
        path=urlsplit(self.path).path
        try:
            if path=='/api/ingest':return self.ingest()
            if self.headers.get('X-OpenOps-Request')!='1':raise PermissionError('Same-origin application header required')
            origin=self.headers.get('Origin')
            if origin and urlsplit(origin).netloc!=self.headers.get('Host'):raise PermissionError('Cross-origin request rejected')
            body=self.read_body()
            with connection() as db:
                db.row_factory=dict_row
                if path=='/api/login':
                    result=access.login(db,body.get('username',''),body.get('password',''),self.client_address[0])
                    if not result:
                        self.reply(401,{'error':'Invalid credentials or temporarily locked account'});return
                    token,user=result
                    db.commit()
                    self.reply(200,{'user':user},'openops_session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800');return
                user=self.identity(db)
                if not user:self.reply(401,{'error':'Login required'});return
                if path=='/api/logout':
                    if self.session():db.execute('DELETE FROM sessions WHERE digest=%s',(access.digest(self.session()),))
                    access.audit(db,user['username'],'session.logout',{})
                    result={};cookie='openops_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
                elif path=='/api/account/password':
                    encoded=db.execute('SELECT password_hash FROM users WHERE id=%s',(user['id'],)).fetchone()['password_hash']
                    if not access.verify_password(body.get('current_password',''),encoded):raise ValueError('Current password is incorrect')
                    db.execute('UPDATE users SET password_hash=%s WHERE id=%s',(access.password_hash(body.get('password')),user['id']))
                    db.execute('DELETE FROM sessions WHERE user_id=%s',(user['id'],));access.audit(db,user['username'],'account.password_changed',{})
                    result={'login_required':True};cookie='openops_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
                elif path.startswith('/api/admin/'):
                    result=access.change(db,user,path.rsplit('/',1)[1],body);cookie=None
                elif path=='/api/monitors/configure':
                    access.require(user,'manager');mid=monitoring.configure(db,body,user['username'])
                    access.audit(db,user['username'],'monitor.'+body.get('action','save'),{'id':mid});result={'id':mid};cookie=None
                elif path=='/api/alerts/acknowledge':
                    access.require(user,'operator');monitoring.acknowledge(db,int(body['id']),body,user['username'])
                    access.audit(db,user['username'],'alert.acknowledgement',{'id':int(body['id']),'acknowledged':body.get('acknowledged',True)})
                    result={};cookie=None
                elif path=='/api/investigations/start':
                    access.require(user,'operator');run_id=investigation.enqueue(db,int(body['alert_id']),body.get('retry') is True,body.get('new_run') is True)
                    access.audit(db,user['username'],'investigation.requested',{'run_id':run_id,'alert_id':int(body['alert_id'])});result={'run_id':run_id};cookie=None
                else:self.reply(404,{'error':'Not found'});return
            self.reply(200,{'status':'updated',**result},cookie)
        except PermissionError as error:self.reply(403,{'error':str(error)})
        except (ValueError,TypeError,KeyError,OverflowError,RecursionError,AttributeError) as error:self.reply(400,{'error':str(error)[:250]})
        except psycopg.IntegrityError:self.reply(400,{'error':'Duplicate name or referenced record is still in use'})
        except psycopg.Error:self.reply(503,{'error':'Storage unavailable'})
        except (TimeoutError,OSError):self.close_connection=True
    def ingest(self):
        token=self.bearer()
        if not token:self.reply(401,{'error':'Ingestion credential required'});return
        allowed=None
        with connection() as db:
            db.row_factory=dict_row
            host=db.execute('SELECT id FROM managed_hosts WHERE ingest_digest=%s AND enabled',(access.digest(token),)).fetchone()
            if host:allowed=host['id']
            elif hmac.compare_digest(token,os.environ['OPENOPS_INGEST_TOKEN']):
                host=db.execute('SELECT id FROM managed_hosts WHERE id=%s AND enabled',(os.environ['OPENOPS_HOST_ID'],)).fetchone()
                if host:allowed=host['id']
        if not allowed:self.reply(401,{'error':'Invalid or disabled host ingestion credential'});return
        try:
            events=validate(self.read_body(2*1024*1024),allowed)
            result=persist(events);log('batch.committed',inserted=result['inserted'],duplicates=result['duplicates'])
            self.reply(200,result)
        except EventConflict:self.reply(409,{'error':'Event ID conflicts with stored content; batch rolled back'})
    def do_GET(self):
        path=urlsplit(self.path).path;query=parse_qs(urlsplit(self.path).query)
        if path in ('/','/console.css','/console.js','/admin.js'):
            asset='index.html' if path=='/' else path[1:]
            raw=(Path('/app/receiver')/asset).read_bytes();self.send_response(200)
            self.send_header('Content-Type',('text/css' if path.endswith('.css') else 'application/javascript' if path.endswith('.js') else 'text/html')+'; charset=utf-8');self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers();self.wfile.write(raw);return
        if path in ('/health/live','/health/ready'):
            try:
                if path.endswith('ready'):
                    with connection() as db:db.execute('SELECT 1 FROM receiver_schema')
                self.reply(200,{'status':'ok','service':'openops-receiver'})
            except psycopg.Error:self.reply(503,{'status':'storage_unavailable'})
            return
        try:
            with connection() as db:
                db.row_factory=dict_row;user=self.identity(db)
                legacy=self.bearer() and hmac.compare_digest(self.bearer(),os.environ['OPENOPS_READ_TOKEN'])
                if not user and not (legacy and path in ('/api/hosts','/api/events')):self.reply(401,{'error':'Login required'});return
                if path=='/api/me':result={'user':user}
                elif path=='/api/admin':
                    access.require(user,'admin');result=access.admin_data(db)
                elif path=='/api/dashboard':
                    host=query.get('host_id',[None])[0] or None
                    result=monitoring.dashboard(db,host)
                    logfile=Path(os.environ.get('OPENOPS_LOG_DIR','/app/logs'))/'receiver.jsonl'
                    runtime=[]
                    if logfile.exists():
                        with logfile.open('rb') as stream:
                            length=stream.seek(0,2);stream.seek(max(0,length-65536));lines=stream.read().decode(errors='replace').splitlines()
                        for line in lines[1:] if length>65536 else lines:
                            try:
                                entry=json.loads(line);runtime.append({k:v for k,v in entry.items() if k in ('timestamp','action','source','status','error_type','inserted','duplicates')})
                            except ValueError:pass
                    result['runtime_logs']=runtime[-100:]
                    result['investigations']=db.execute("SELECT i.id,i.alert_id,i.status,i.attempts,i.created_at,i.finished_at,i.error_type FROM investigations i JOIN alerts a ON a.id=i.alert_id JOIN monitors m ON m.id=a.monitor_id WHERE (%s::text IS NULL OR m.host_id=%s) ORDER BY i.created_at DESC LIMIT 50",(host,host)).fetchall()
                elif path.startswith('/api/investigations/'):
                    run_id=path.rsplit('/',1)[1];result=db.execute('SELECT * FROM investigations WHERE id=%s',(run_id,)).fetchone()
                    if result:result['trace']=db.execute('SELECT happened_at,action,detail FROM investigation_trace WHERE run_id=%s ORDER BY id',(run_id,)).fetchall()
                    else:self.reply(404,{'error':'Unknown investigation'});return
                elif path.startswith('/api/world/'):
                    run_id=path.rsplit('/',1)[1]
                    item=db.execute('SELECT a.opening_evidence,i.attempts,i.manifest FROM investigations i JOIN alerts a ON a.id=i.alert_id WHERE i.id=%s',(run_id,)).fetchone()
                    if not item:self.reply(404,{'error':'Unknown investigation'});return
                    key=(item['manifest'] or {}).get('world_context_key',run_id+':attempt:'+str(item['attempts']))
                    result=investigation.ContextBuilderService(investigation.WorldStoreService(db)).build(key,float(item['opening_evidence']['observed_epoch']))
                elif path=='/api/hosts':
                    result={'hosts':db.execute("SELECT host_id,count(*) samples,max(observed_at) latest_observed_at,max(received_at) latest_received_at,extract(epoch FROM clock_timestamp()-max(observed_at)) observation_age_seconds FROM telemetry_events GROUP BY host_id ORDER BY host_id").fetchall()}
                elif path=='/api/events':
                    limit=int(query.get('limit',['20'])[0])
                    if not 1<=limit<=100:raise ValueError('Invalid limit')
                    result={'events':[{'telemetry':r['payload'],'received_at':r['received_at']} for r in db.execute('SELECT payload,received_at FROM telemetry_events ORDER BY observed_at DESC,event_id LIMIT %s',(limit,)).fetchall()]}
                else:self.reply(404,{'error':'Not found'});return
            self.reply(200,result)
        except PermissionError as error:self.reply(403,{'error':str(error)})
        except (ValueError,TypeError):self.reply(400,{'error':'Invalid query'})
        except psycopg.Error:self.reply(503,{'error':'Storage unavailable'})


def main():
    for key in ("OPENOPS_INGEST_TOKEN", "OPENOPS_READ_TOKEN"):
        if len(os.environ.get(key, "")) < 24:
            raise SystemExit("Configure private receiver credentials before startup")
    initialize()
    log("receiver.started", schema_version=1)
    if os.environ.get("OPENOPS_MONITOR_ENABLED", "true") == "true":
        threading.Thread(target=monitoring.loop,args=(connection,log),daemon=True).start()
    if os.environ.get("OPENOPS_INVESTIGATION_ENABLED", "false") == "true":
        threading.Thread(target=investigation.loop,args=(connection,log),daemon=True).start()
    threading.Thread(target=notifications.loop,args=(connection,log),daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("OPENOPS_PORT", "8096"))), Handler).serve_forever()


if __name__ == "__main__":
    main()
