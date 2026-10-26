"""Password sessions, user-owned API credentials and administrator configuration."""
import base64
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit
from cryptography.fernet import Fernet
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROLES = {"admin":3,"manager":2,"operator":1}
DDL = """
CREATE TABLE IF NOT EXISTS users(id serial PRIMARY KEY,username text UNIQUE NOT NULL,password_hash text NOT NULL,
 role text NOT NULL CHECK(role IN ('admin','manager','operator')),enabled boolean NOT NULL DEFAULT true,created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS sessions(digest text PRIMARY KEY,user_id integer REFERENCES users(id),expires_at timestamptz NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts(key text PRIMARY KEY, failures integer NOT NULL DEFAULT 0,updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS user_tokens(id serial PRIMARY KEY,name text NOT NULL,digest text UNIQUE NOT NULL,user_id integer NOT NULL REFERENCES users(id),
 expires_at timestamptz NOT NULL,revoked boolean DEFAULT false,created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS clients(id serial PRIMARY KEY,name text UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS managed_hosts(id text PRIMARY KEY,name text NOT NULL,client_id integer REFERENCES clients(id),address text NOT NULL DEFAULT '',
 enabled boolean DEFAULT true,ingest_digest text,created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS ticket_servers(id serial PRIMARY KEY,name text NOT NULL,url text NOT NULL,enabled boolean DEFAULT true);
CREATE TABLE IF NOT EXISTS connectors(id serial PRIMARY KEY,name text NOT NULL,kind text NOT NULL,enabled boolean DEFAULT false,
 config jsonb NOT NULL DEFAULT '{}',secret text NOT NULL DEFAULT '',created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS system_activity(id bigserial PRIMARY KEY,happened_at timestamptz DEFAULT now(),actor text NOT NULL,action text NOT NULL,detail jsonb NOT NULL);
"""

def digest(value):return hashlib.sha256(value.encode()).hexdigest()

def password_hash(value):
    if not isinstance(value,str) or not 12 <= len(value) <= 256:raise ValueError("Use a password between 12 and 256 characters")
    salt=secrets.token_hex(16)
    return salt+":"+hashlib.pbkdf2_hmac('sha256',value.encode(),salt.encode(),600000).hex()

def verify_password(value,encoded):
    if not isinstance(value,str) or len(value)>256:return False
    salt,expected=encoded.split(':',1)
    return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',value.encode(),salt.encode(),600000).hex(),expected)

def audit(db,actor,action,detail):
    db.execute("INSERT INTO system_activity(actor,action,detail) VALUES(%s,%s,%s)",(actor,action,Jsonb(detail)))

def initialize(db):
    db.execute(DDL)
    db.execute("SELECT pg_advisory_xact_lock(809602)")
    if not db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        password=secrets.token_urlsafe(20)
        db.execute("INSERT INTO users(username,password_hash,role) VALUES('admin',%s,'admin')",(password_hash(password),))
        destination=Path(os.environ.get('OPENOPS_LOG_DIR','/app/logs'))/'bootstrap-admin.txt'
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text('OpenOps initial administrator\nUsername: admin\nPassword: '+password+'\nChange this password after login.\n')
        destination.chmod(0o600)
    db.execute("INSERT INTO managed_hosts(id,name,address) VALUES(%s,'TeleMediation server','192.168.1.202') ON CONFLICT DO NOTHING",(os.environ.get('OPENOPS_HOST_ID','tmc-lab-01'),))

def login(db,username,password,peer):
    key=digest(peer+':'+str(username).lower()[:80])
    db.execute("INSERT INTO login_attempts(key) VALUES(%s) ON CONFLICT DO NOTHING",(key,))
    attempt=db.execute("SELECT failures,updated_at>now()-interval '15 minutes' AS recent FROM login_attempts WHERE key=%s FOR UPDATE",(key,)).fetchone()
    if attempt['recent'] and attempt['failures']>=8:return None
    user=db.execute("SELECT * FROM users WHERE username=%s",(str(username).lower()[:80],)).fetchone()
    # Hash an unknown account too, avoiding the obvious fast path.
    encoded=user['password_hash'] if user else '0'*32+':'+ '0'*64
    valid=verify_password(password,encoded)
    if not user or not user['enabled'] or not valid:
        db.execute("UPDATE login_attempts SET failures=CASE WHEN updated_at<now()-interval '15 minutes' THEN 1 ELSE failures+1 END,updated_at=now() WHERE key=%s",(key,))
        return None
    db.execute("DELETE FROM login_attempts WHERE key=%s",(key,))
    token=secrets.token_urlsafe(40)
    db.execute("DELETE FROM sessions WHERE expires_at<now()")
    db.execute("INSERT INTO sessions(digest,user_id,expires_at) VALUES(%s,%s,now()+interval '8 hours')",(digest(token),user['id']))
    audit(db,user['username'],'session.login',{})
    return token,public_user(user)

def public_user(user):return {k:user[k] for k in ('id','username','role','enabled')}

def principal(db,bearer=None,session=None):
    if bearer:
        user=db.execute("SELECT u.* FROM user_tokens t JOIN users u ON u.id=t.user_id WHERE t.digest=%s AND NOT t.revoked AND t.expires_at>now() AND u.enabled",(digest(bearer),)).fetchone()
    elif session:
        user=db.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.digest=%s AND s.expires_at>now() AND u.enabled",(digest(session),)).fetchone()
    else:user=None
    return public_user(user) if user else None

def require(user,role):
    if not user or ROLES[user['role']]<ROLES[role]:raise PermissionError('Insufficient permissions')

def text(value,maximum=120):
    if not isinstance(value,str) or not 1<=len(value.strip())<=maximum:raise ValueError('Invalid text field')
    return value.strip()

def url(value):
    value=text(value,1000);parsed=urlsplit(value)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:raise ValueError('Use an HTTP(S) URL without embedded credentials')
    return value

def cipher():
    key=os.environ.get('OPENOPS_ADMIN_TOKEN','')
    if len(key)<24:raise ValueError('Server encryption key is not configured')
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))

def admin_data(db):
    return {'users':db.execute('SELECT id,username,role,enabled,created_at FROM users ORDER BY id').fetchall(),
      'tokens':db.execute('SELECT t.id,t.name,t.user_id,u.username,t.expires_at,t.revoked FROM user_tokens t JOIN users u ON u.id=t.user_id ORDER BY t.id').fetchall(),
      'clients':db.execute('SELECT * FROM clients ORDER BY id').fetchall(),
      'hosts':db.execute('SELECT id,name,client_id,address,enabled FROM managed_hosts ORDER BY name').fetchall(),
      'ticket_servers':db.execute('SELECT * FROM ticket_servers ORDER BY id').fetchall(),
      'connectors':db.execute("SELECT id,name,kind,enabled,config,(secret<>'') AS has_secret FROM connectors ORDER BY id").fetchall()}

def change(db,user,resource,data):
    require(user,'admin');actor=user['username'];result={}
    action=data.get('action','save');ident=data.get('id')
    if resource=='users':
        db.execute('SELECT pg_advisory_xact_lock(809603)')
        if ident:
            current=db.execute('SELECT * FROM users WHERE id=%s FOR UPDATE',(int(ident),)).fetchone()
            if not current:raise ValueError('Unknown user')
            role=data.get('role',current['role']);enabled=data.get('enabled',current['enabled'])
            if action=='delete':enabled=False
            if role not in ROLES or type(enabled) is not bool:raise ValueError('Invalid role or enabled setting')
            if current['role']=='admin' and current['enabled'] and (role!='admin' or not enabled):
                if db.execute("SELECT count(*) n FROM users WHERE role='admin' AND enabled").fetchone()['n']<=1:raise ValueError('Keep at least one enabled administrator')
            db.execute('UPDATE users SET role=%s,enabled=%s WHERE id=%s',(role,enabled,int(ident)))
            if data.get('password'):
                db.execute('UPDATE users SET password_hash=%s WHERE id=%s',(password_hash(data['password']),int(ident)))
                db.execute('DELETE FROM sessions WHERE user_id=%s',(int(ident),))
            if not enabled:db.execute('DELETE FROM sessions WHERE user_id=%s',(int(ident),))
        else:
            username=text(data.get('username'),80).lower()
            if not re.fullmatch(r'[a-z0-9._@-]+',username) or data.get('role') not in ROLES:raise ValueError('Invalid username or role')
            enabled=data.get('enabled',True)
            if type(enabled) is not bool:raise ValueError('Invalid enabled setting')
            ident=db.execute('INSERT INTO users(username,password_hash,role,enabled) VALUES(%s,%s,%s,%s) RETURNING id',(username,password_hash(data.get('password')),data['role'],enabled)).fetchone()['id']
    elif resource=='tokens':
        if action=='revoke':db.execute('UPDATE user_tokens SET revoked=true WHERE id=%s',(int(ident),))
        else:
            owner=db.execute('SELECT id FROM users WHERE id=%s AND enabled',(int(data['user_id']),)).fetchone()
            if not owner:raise ValueError('Unknown or disabled user')
            days=int(data.get('days',30))
            if not 1<=days<=365:raise ValueError('Token lifetime must be 1..365 days')
            if ident:
                changed=db.execute("UPDATE user_tokens SET name=%s,user_id=%s,expires_at=now()+%s*interval '1 day' WHERE id=%s AND NOT revoked RETURNING id",(text(data['name']),owner['id'],days,int(ident))).fetchone()
                if not changed:raise ValueError('Unknown or revoked token')
            else:
                token=secrets.token_urlsafe(40)
                ident=db.execute("INSERT INTO user_tokens(name,digest,user_id,expires_at) VALUES(%s,%s,%s,now()+%s*interval '1 day') RETURNING id",(text(data['name']),digest(token),owner['id'],days)).fetchone()['id']
                result['token']=token
    elif resource=='hosts':
        ident=text(data['id'],120)
        if not re.fullmatch(r'[a-zA-Z0-9._-]+',ident):raise ValueError('Use letters, numbers, dots, underscores or hyphens for host ID')
        current=db.execute('SELECT * FROM managed_hosts WHERE id=%s',(ident,)).fetchone()
        if action=='delete':
            if db.execute('SELECT 1 FROM monitors WHERE host_id=%s AND NOT deleted',(ident,)).fetchone():raise ValueError('Delete host monitors before retiring this host')
            db.execute('UPDATE managed_hosts SET enabled=false WHERE id=%s',(ident,))
        else:
            enabled=data.get('enabled',True)
            if type(enabled) is not bool:raise ValueError('Invalid enabled setting')
            db.execute("INSERT INTO managed_hosts(id,name,client_id,address,enabled) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET name=excluded.name,client_id=excluded.client_id,address=excluded.address,enabled=excluded.enabled",(ident,text(data['name']),int(data['client_id']) if data.get('client_id') else None,str(data.get('address',''))[:253],enabled))
            if not current or data.get('rotate_token'):
                token=secrets.token_urlsafe(40);db.execute('UPDATE managed_hosts SET ingest_digest=%s WHERE id=%s',(digest(token),ident));result['token']=token
    elif resource=='clients':
        if action=='delete':db.execute('DELETE FROM clients WHERE id=%s',(int(ident),))
        elif ident:db.execute('UPDATE clients SET name=%s WHERE id=%s',(text(data['name']),int(ident)))
        else:ident=db.execute('INSERT INTO clients(name) VALUES(%s) RETURNING id',(text(data['name']),)).fetchone()['id']
    elif resource=='ticket_servers':
        if action=='delete':db.execute('UPDATE ticket_servers SET enabled=false WHERE id=%s',(int(ident),))
        elif ident:db.execute('UPDATE ticket_servers SET name=%s,url=%s,enabled=%s WHERE id=%s',(text(data['name']),url(data['url']),bool(data.get('enabled',True)),int(ident)))
        else:ident=db.execute('INSERT INTO ticket_servers(name,url,enabled) VALUES(%s,%s,%s) RETURNING id',(text(data['name']),url(data['url']),bool(data.get('enabled',True)))).fetchone()['id']
    elif resource=='connectors':
        if action=='delete':db.execute('UPDATE connectors SET enabled=false WHERE id=%s',(int(ident),))
        else:
            kind=data['kind'];config=data.get('config',{});enabled=data.get('enabled',False)
            if kind not in ('webhook','sms','email') or not isinstance(config,dict) or type(enabled) is not bool:raise ValueError('Invalid connector')
            allowed={'url','to'} if kind in ('webhook','sms') else {'host','port','username','from','to','starttls'}
            if set(config)-allowed:raise ValueError('Unknown configuration key; put credentials in the secret field')
            if kind in ('webhook','sms'):
                config['url']=url(config.get('url'))
                if kind=='sms':config['to']=text(config.get('to'),80)
            else:
                for k in ('host','from','to'):config[k]=text(config.get(k),253)
                config['port']=int(config.get('port',587))
                if not 1<=config['port']<=65535:raise ValueError('Invalid SMTP port')
                config['starttls']=True
            # Connector secrets are encrypted; never returned in configuration responses.
            secret=cipher().encrypt(text(data['secret'],4096).encode()).decode() if data.get('secret') else ''
            if ident:db.execute("UPDATE connectors SET name=%s,kind=%s,enabled=%s,config=%s,secret=CASE WHEN %s='' THEN secret ELSE %s END WHERE id=%s",(text(data['name']),kind,enabled,Jsonb(config),secret,secret,int(ident)))
            else:ident=db.execute('INSERT INTO connectors(name,kind,enabled,config,secret) VALUES(%s,%s,%s,%s,%s) RETURNING id',(text(data['name']),kind,enabled,Jsonb(config),secret)).fetchone()['id']
    else:raise ValueError('Unknown administration resource')
    audit(db,actor,'admin.'+resource+'.'+action,{'id':ident})
    return {'id':ident,**result}
