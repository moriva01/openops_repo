"""Opt-in notification outbox. No external delivery before a connector is enabled."""
import json
import smtplib
import ssl
import time
import urllib.request
from email.message import EmailMessage
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from receiver.access import audit,cipher

DDL="""
CREATE TABLE IF NOT EXISTS notification_deliveries(id bigserial PRIMARY KEY,history_id bigint NOT NULL,
 connector_id integer NOT NULL,connector_name text NOT NULL,payload jsonb NOT NULL,status text NOT NULL DEFAULT 'queued',
 attempts integer NOT NULL DEFAULT 0,next_at timestamptz DEFAULT now(),last_error text,created_at timestamptz DEFAULT now(),finished_at timestamptz,
 UNIQUE(history_id,connector_id));
"""

def initialize(db):db.execute(DDL)

def enqueue(db,history_id,alert_id,action,evidence):
    if action not in ('opened','resolved','severity_changed'):return
    if not db.execute("SELECT to_regclass('notification_deliveries') AS relation").fetchone()['relation']:return
    alert=db.execute('SELECT a.severity,m.name,m.host_id FROM alerts a JOIN monitors m ON m.id=a.monitor_id WHERE a.id=%s',(alert_id,)).fetchone()
    payload={'schema':'openops.notification.v1','event_id':history_id,'alert_id':alert_id,'action':action,
             'severity':'clear' if action=='resolved' else alert['severity'],'monitor':alert['name'],'host_id':alert['host_id'],'evidence':evidence}
    for c in db.execute('SELECT id,name FROM connectors WHERE enabled').fetchall():
        db.execute('INSERT INTO notification_deliveries(history_id,connector_id,connector_name,payload) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(history_id,c['id'],c['name'],Jsonb(payload)))

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def send(connector,payload,delivery_id):
    config=connector['config'];secret=cipher().decrypt(connector['secret'].encode()).decode() if connector['secret'] else ''
    if connector['kind']=='email':
        message=EmailMessage();message['From']=config['from'];message['To']=config['to']
        message['Subject']='OpenOps '+payload['severity'].upper()+' · '+payload['monitor']
        message.set_content(json.dumps(payload,indent=2))
        with smtplib.SMTP(config['host'],config['port'],timeout=10) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if config.get('username'):smtp.login(config['username'],secret)
            smtp.send_message(message)
    else:
        body=payload if connector['kind']=='webhook' else {'to':config.get('to'),'message':'OpenOps '+payload['severity']+': '+payload['monitor'],'event':payload}
        headers={'Content-Type':'application/json','Idempotency-Key':'openops-delivery-'+str(delivery_id)}
        if secret:headers['Authorization']='Bearer '+secret
        request=urllib.request.Request(config['url'],data=json.dumps(body).encode(),headers=headers)
        with urllib.request.build_opener(NoRedirect).open(request,timeout=10) as response:
            if not 200<=response.status<300:raise ValueError('Delivery rejected')
            response.read(1024)

def loop(connection,logger):
    while True:
        job=None
        try:
            with connection() as db:
                db.row_factory=dict_row
                db.execute("UPDATE notification_deliveries SET status='queued',next_at=now() WHERE status='sending' AND next_at<now()-interval '2 minutes'")
                job=db.execute("SELECT d.*,c.kind,c.config,c.secret,c.enabled FROM notification_deliveries d LEFT JOIN connectors c ON c.id=d.connector_id WHERE d.status='queued' AND d.next_at<=now() ORDER BY d.id FOR UPDATE OF d SKIP LOCKED LIMIT 1").fetchone()
                if job:db.execute("UPDATE notification_deliveries SET status='sending',attempts=attempts+1,next_at=now() WHERE id=%s",(job['id'],))
            if job:
                if not job['enabled']:
                    with connection() as db:db.execute("UPDATE notification_deliveries SET status='cancelled',finished_at=now() WHERE id=%s",(job['id'],))
                else:
                    send(job,job['payload'],job['id'])
                    with connection() as db:
                        db.execute("UPDATE notification_deliveries SET status='delivered',finished_at=now(),last_error=NULL WHERE id=%s",(job['id'],))
                        audit(db,'notification worker','notification.delivered',{'delivery_id':job['id'],'connector':job['connector_name'],'alert_id':job['payload']['alert_id']})
        except Exception as error:
            logger('notification.error',error_type=type(error).__name__)
            if job:
                with connection() as db:
                    status='failed' if job['attempts']>=4 else 'queued'
                    db.execute("UPDATE notification_deliveries SET status=%s,last_error=%s,next_at=now()+%s*interval '1 second' WHERE id=%s",(status,type(error).__name__,min(900,15*2**job['attempts']),job['id']))
                    audit(db,'notification worker','notification.'+status,{'delivery_id':job['id'],'error_type':type(error).__name__})
        time.sleep(3)
