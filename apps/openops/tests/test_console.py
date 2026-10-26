"""Role enforcement, host isolation, severity transitions and notification contracts."""
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
import uuid
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from unittest.mock import patch
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from receiver import access,monitoring,notifications,server

class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.schema='test_console_'+uuid.uuid4().hex
        self.old=os.environ.get('PGOPTIONS');self.oldlog=os.environ.get('OPENOPS_LOG_DIR')
        self.temp=tempfile.TemporaryDirectory();os.environ['OPENOPS_LOG_DIR']=self.temp.name
        with psycopg.connect() as db:db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        os.environ['PGOPTIONS']='-c search_path='+self.schema
        server.initialize()
        self.db=server.connection();self.db.row_factory=dict_row
        self.admin=access.public_user(self.db.execute("SELECT * FROM users WHERE username='admin'").fetchone())
    def tearDown(self):
        self.db.rollback();self.db.close()
        if self.old is None:os.environ.pop('PGOPTIONS',None)
        else:os.environ['PGOPTIONS']=self.old
        if self.oldlog is None:os.environ.pop('OPENOPS_LOG_DIR',None)
        else:os.environ['OPENOPS_LOG_DIR']=self.oldlog
        with psycopg.connect() as db:db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.temp.cleanup()
    def create_user(self,role):
        return access.change(self.db,self.admin,'users',{'username':role,'password':'A-long-test-password-123','role':role})['id']
    def test_bootstrap_only_admin_and_hashed_password(self):
        users=self.db.execute('SELECT * FROM users').fetchall();self.assertEqual(len(users),1)
        password=Path(self.temp.name,'bootstrap-admin.txt').read_text().split('Password: ')[1].splitlines()[0]
        self.assertTrue(access.verify_password(password,users[0]['password_hash']))
        self.assertNotIn(password,users[0]['password_hash'])
    def test_password_login_session_disabled_user_and_token_revocation(self):
        uid=self.create_user('operator')
        self.assertIsNone(access.login(self.db,'operator','incorrect','test-peer'))
        token,u=access.login(self.db,'operator','A-long-test-password-123','test-peer')
        self.assertEqual(access.principal(self.db,session=token)['role'],'operator')
        issued=access.change(self.db,self.admin,'tokens',{'name':'test','user_id':uid,'days':1})
        self.assertEqual(access.principal(self.db,bearer=issued['token'])['id'],uid)
        access.change(self.db,self.admin,'tokens',{'id':issued['id'],'name':'Reassigned','user_id':self.admin['id'],'days':1})
        self.assertEqual(access.principal(self.db,bearer=issued['token'])['role'],'admin')
        access.change(self.db,self.admin,'tokens',{'id':issued['id'],'action':'revoke'})
        self.assertIsNone(access.principal(self.db,bearer=issued['token']))
        access.change(self.db,self.admin,'users',{'id':uid,'enabled':False})
        self.assertIsNone(access.principal(self.db,session=token))
    def test_last_administrator_cannot_be_disabled(self):
        with self.assertRaises(ValueError):access.change(self.db,self.admin,'users',{'id':self.admin['id'],'enabled':False})
    def test_severity_moves_up_down_and_resolves_without_duplicate_alert(self):
        host=os.environ['OPENOPS_HOST_ID']
        m=dict(self.db.execute('SELECT * FROM monitors').fetchone());m.update(metric='cpu_percent',thresholds=[{'severity':'warning','value':50},{'severity':'major','value':70},{'severity':'critical','value':90}],duration_seconds=0)
        monitoring.configure(self.db,m)
        now=time.time()
        for i,(value,severity) in enumerate([(55,'warning'),(95,'critical'),(75,'major')]):
            monitoring.evaluate(self.db,{'host_id':host,'event_id':str(uuid.uuid4()),'observed_epoch':now+i*15,'cpu_percent':value},now+i*15,host_id=host)
            self.assertEqual(self.db.execute('SELECT severity FROM alerts').fetchone()['severity'],severity)
        for i in (3,4):monitoring.evaluate(self.db,{'host_id':host,'event_id':str(uuid.uuid4()),'observed_epoch':now+i*15,'cpu_percent':10},now+i*15,host_id=host)
        rows=self.db.execute('SELECT * FROM alerts').fetchall();self.assertEqual(len(rows),1);self.assertIsNotNone(rows[0]['resolved_at'])
    def test_host_scope_and_below_threshold(self):
        access.change(self.db,self.admin,'hosts',{'id':'second','name':'Second host'})
        mid=monitoring.configure(self.db,{'host_id':'second','name':'Low CPU','metric':'cpu_percent','duration_seconds':0,'recovery_samples':1,'enabled':True,'comparator':'below','thresholds':[{'severity':'warning','value':30},{'severity':'critical','value':10}]})
        now=time.time();row={'host_id':os.environ['OPENOPS_HOST_ID'],'event_id':str(uuid.uuid4()),'observed_epoch':now,'cpu_percent':5}
        monitoring.evaluate(self.db,row,now,host_id=row['host_id'])
        self.assertEqual(self.db.execute('SELECT state FROM monitors WHERE id=%s',(mid,)).fetchone()['state'],'normal')
        row['host_id']='second';monitoring.evaluate(self.db,row,now,host_id='second')
        self.assertEqual(self.db.execute('SELECT severity FROM alerts WHERE monitor_id=%s',(mid,)).fetchone()['severity'],'critical')
    def test_acknowledgement_ticket_and_unacknowledgement(self):
        host=os.environ['OPENOPS_HOST_ID'];m=self.db.execute('SELECT * FROM monitors').fetchone();self.db.execute('UPDATE monitors SET duration_seconds=0')
        monitoring.evaluate(self.db,{'host_id':host,'event_id':str(uuid.uuid4()),'observed_epoch':time.time(),'voice_pending':2,'app_reachable':'true'},time.time())
        aid=self.db.execute('SELECT id FROM alerts').fetchone()['id'];ticket=access.change(self.db,self.admin,'ticket_servers',{'name':'Issue tracker','url':'https://example.com/browse'})
        monitoring.acknowledge(self.db,aid,{'ticket_server_id':ticket['id'],'ticket_ref':'TK 12345'},'operator')
        row=self.db.execute('SELECT * FROM alerts').fetchone();self.assertEqual(row['ticket_url'],'https://example.com/browse/TK%2012345');self.assertEqual(row['acknowledged_by'],'operator')
        monitoring.acknowledge(self.db,aid,{'acknowledged':False},'operator');self.assertIsNone(self.db.execute('SELECT acknowledged_at FROM alerts').fetchone()['acknowledged_at'])
    def test_connector_secret_is_encrypted_and_disabled_connector_does_not_queue(self):
        c=access.change(self.db,self.admin,'connectors',{'name':'Webhook','kind':'webhook','config':{'url':'https://example.com/hook'},'secret':'private-test-secret'})
        stored=self.db.execute('SELECT * FROM connectors WHERE id=%s',(c['id'],)).fetchone();self.assertNotIn('private-test-secret',stored['secret']);self.assertEqual(access.cipher().decrypt(stored['secret'].encode()).decode(),'private-test-secret')
        public=access.admin_data(self.db)['connectors'][0];self.assertNotIn('secret',public)
        self.db.execute('UPDATE monitors SET duration_seconds=0');host=os.environ['OPENOPS_HOST_ID']
        monitoring.evaluate(self.db,{'host_id':host,'event_id':str(uuid.uuid4()),'observed_epoch':time.time(),'voice_pending':2,'app_reachable':'true'},time.time())
        self.assertEqual(self.db.execute('SELECT count(*) n FROM notification_deliveries').fetchone()['n'],0)
    def test_enabled_connector_outbox_is_idempotent(self):
        access.change(self.db,self.admin,'connectors',{'name':'Enabled local fixture','kind':'webhook','enabled':True,'config':{'url':'http://127.0.0.1:9999/hook'}})
        self.db.execute('UPDATE monitors SET duration_seconds=0');host=os.environ['OPENOPS_HOST_ID']
        sample={'host_id':host,'event_id':str(uuid.uuid4()),'observed_epoch':time.time(),'voice_pending':2,'app_reachable':'true'}
        monitoring.evaluate(self.db,sample,time.time())
        row=self.db.execute('SELECT * FROM notification_deliveries').fetchone();self.assertEqual(row['payload']['action'],'opened')
        notifications.enqueue(self.db,row['history_id'],row['payload']['alert_id'],'opened',row['payload']['evidence'])
        self.assertEqual(self.db.execute('SELECT count(*) n FROM notification_deliveries').fetchone()['n'],1)
        self.assertEqual(row['status'],'queued')
    def test_expired_sessions_and_credentials_do_not_authorize(self):
        uid=self.create_user('operator');token,u=access.login(self.db,'operator','A-long-test-password-123','peer')
        self.db.execute("UPDATE sessions SET expires_at=now()-interval '1 second'")
        self.assertIsNone(access.principal(self.db,session=token))
        issued=access.change(self.db,self.admin,'tokens',{'name':'Expired fixture','user_id':uid,'days':1})
        self.db.execute("UPDATE user_tokens SET expires_at=now()-interval '1 second'")
        self.assertIsNone(access.principal(self.db,bearer=issued['token']))
    def test_signed_url_is_private_and_survives_edit(self):
        endpoint='https://example.test/workflow?sig=synthetic-private-signature'
        c=access.change(self.db,self.admin,'connectors',{'name':'Teams','kind':'teams','config':{'url':endpoint}})
        stored=self.db.execute('SELECT * FROM connectors WHERE id=%s',(c['id'],)).fetchone()
        self.assertNotIn('url',stored['config'])
        self.assertEqual(access.cipher().decrypt(stored['encrypted_url'].encode()).decode(),endpoint)
        self.assertNotIn(endpoint,str(access.admin_data(self.db)))
        access.change(self.db,self.admin,'connectors',{'id':c['id'],'name':'Renamed Teams','kind':'teams','config':{}})
        updated=self.db.execute('SELECT encrypted_url FROM connectors WHERE id=%s',(c['id'],)).fetchone()
        self.assertEqual(updated['encrypted_url'],stored['encrypted_url'])

    def test_legacy_endpoint_migration_keeps_destination_without_public_url(self):
        self.db.execute("INSERT INTO connectors(name,kind,config) VALUES('Legacy','webhook',%s)",
                        (psycopg.types.json.Jsonb({'url':'https://example.test/legacy?sig=fixture'}),))
        access.initialize(self.db)
        stored=self.db.execute("SELECT * FROM connectors WHERE name='Legacy'").fetchone()
        self.assertNotIn('url',stored['config'])
        self.assertEqual(access.cipher().decrypt(stored['encrypted_url'].encode()).decode(),'https://example.test/legacy?sig=fixture')

    def test_admin_test_queues_only_a_marked_test(self):
        c=access.change(self.db,self.admin,'connectors',{'name':'Teams','kind':'teams','enabled':True,'config':{'url':'https://example.test/workflow'}})
        before=self.db.execute('SELECT count(*) n FROM alerts').fetchone()['n']
        result=access.change(self.db,self.admin,'connectors',{'id':c['id'],'action':'test'})
        job=self.db.execute('SELECT * FROM notification_deliveries WHERE id=%s',(result['delivery_id'],)).fetchone()
        self.assertTrue(job['payload']['test'])
        self.assertEqual(job['payload']['action'],'test')
        self.assertEqual(self.db.execute('SELECT count(*) n FROM alerts').fetchone()['n'],before)

    def test_actual_local_webhook_delivery_payload_and_idempotency_header(self):
        received=[]
        class Sink(BaseHTTPRequestHandler):
            def do_POST(inner):
                received.append((json.loads(inner.rfile.read(int(inner.headers['Content-Length']))),inner.headers.get('Idempotency-Key')));inner.send_response(204);inner.end_headers()
            def log_message(self,*args):pass
        http=ThreadingHTTPServer(('127.0.0.1',0),Sink);threading.Thread(target=http.serve_forever,daemon=True).start()
        try:
            payload={'severity':'warning','monitor':'Local test','alert_id':1}
            notifications.send({'kind':'webhook','config':{'url':'http://127.0.0.1:'+str(http.server_port)},'secret':''},payload,123)
            self.assertEqual(received,[(payload,'openops-delivery-123')])
        finally:http.shutdown();http.server_close()
    def test_http_role_enforcement_and_host_scoped_ingestion(self):
        for role in ('manager','operator'):self.create_user(role)
        self.db.commit()
        http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
        base='http://127.0.0.1:'+str(http.server_port)
        def request(path,body=None,cookie=None,bearer=None,header=True):
            headers={'Content-Type':'application/json'}
            if header:headers['X-OpenOps-Request']='1'
            if cookie:headers['Cookie']=cookie
            if bearer:headers['Authorization']='Bearer '+bearer
            req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
            with urllib.request.urlopen(req,timeout=10) as response:return json.load(response),response.headers.get('Set-Cookie')
        try:
            for role in ('manager','operator'):
                result,cookie=request('/api/login',{'username':role,'password':'A-long-test-password-123'})
                self.assertIn('HttpOnly',cookie)
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/admin',cookie=cookie)
                self.assertEqual(error.exception.code,403)
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/admin/clients',{'name':'Forbidden'},cookie)
                self.assertEqual(error.exception.code,403)
                if role=='operator':
                    with self.assertRaises(urllib.error.HTTPError) as error:request('/api/monitors/configure',{'id':1,'action':'delete'},cookie)
                    self.assertEqual(error.exception.code,403)
                else:
                    request('/api/monitors/configure',{'host_id':os.environ['OPENOPS_HOST_ID'],'name':'Manager created','metric':'cpu_percent','duration_seconds':30,'recovery_samples':2,'enabled':True,'thresholds':[{'severity':'critical','value':95}]},cookie)
                with self.assertRaises(urllib.error.HTTPError) as error:request('/api/logout',{},cookie,header=False)
                self.assertEqual(error.exception.code,403)
                request('/api/logout',{},cookie)
                with self.assertRaises(urllib.error.HTTPError):request('/api/me',cookie=cookie)
            issued=access.change(self.db,self.admin,'hosts',{'id':'host-two','name':'Second'});self.db.commit()
            from tests.test_receiver import event
            item=event();item['host_id']='host-two';body={'schema':'openops.batch.v1','events':[item]}
            result,_=request('/api/ingest',body,bearer=issued['token']);self.assertEqual(result['inserted'],1)
            item['event_id']=str(uuid.uuid4());item['host_id']=os.environ['OPENOPS_HOST_ID']
            with self.assertRaises(urllib.error.HTTPError) as error:request('/api/ingest',body,bearer=issued['token'])
            self.assertEqual(error.exception.code,400)
        finally:http.shutdown();http.server_close()
