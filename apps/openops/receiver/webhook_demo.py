"""Authenticated local webhook inbox for reproducible delivery demonstrations."""
import hmac
import json
import os
from pathlib import Path
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def connection():
    path = Path(os.environ.get('WEBHOOK_DEMO_DB', '/app/logs/webhook-inbox.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('''CREATE TABLE IF NOT EXISTS receipts(
        id INTEGER PRIMARY KEY, delivery_key TEXT UNIQUE NOT NULL,
        received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        payload TEXT NOT NULL)''')
    return db


def same_value(left, right):
    """JSON numbers compare by value; booleans remain distinct from numbers."""
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_value(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same_value(a, b) for a, b in zip(left, right))
    return left == right


def accept(db, key, payload):
    if not isinstance(key, str) or not 1 <= len(key) <= 160:
        raise ValueError('Idempotency-Key required')
    if not isinstance(payload, dict) or payload.get('schema') != 'openops.notification.v1':
        raise ValueError('Expected openops.notification.v1')
    if payload.get('action') not in ('opened', 'resolved', 'severity_changed'):
        raise ValueError('Unsupported action')
    if type(payload.get('alert_id')) is not int or not isinstance(payload.get('evidence'), dict):
        raise ValueError('Alert identity and evidence required')
    raw = json.dumps(payload, sort_keys=True, allow_nan=False, separators=(',', ':'))
    stored = db.execute('SELECT payload FROM receipts WHERE delivery_key=?', (key,)).fetchone()
    if stored:
        if not same_value(json.loads(stored['payload']), payload):
            raise ValueError('Delivery key conflicts with stored content')
        return False
    db.execute('INSERT INTO receipts(delivery_key,payload) VALUES(?,?)', (key, raw))
    return True


PAGE = b'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenOps | Webhook inbox</title>
<style>body{font:15px system-ui;background:#eef3f8;color:#17304c;margin:35px auto;padding:0 20px;max-width:1000px}input,button{font:inherit;padding:12px;border:1px solid #b8cadb;border-radius:6px;margin:4px}input{max-width:70%;width:420px}article{background:white;border:1px solid #d6e1ed;padding:20px;border-radius:10px;margin:16px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}h2{font-size:18px}.opened{color:#ba6b08}.resolved{color:#14764b}</style>
<h1>Webhook delivery inbox</h1><p>Local authenticated receiver. Opening and recovery messages share an alert ID.</p><input id="token" type="password" placeholder="Webhook inbox token" aria-label="Webhook inbox token"><button id="connect">Connect</button><p id="status"></p><main id="receipts"></main>
<script>let token='',timer;async function refresh(){try{let r=await fetch('/api/receipts',{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw Error('Inbox credential required');let d=await r.json();document.getElementById('status').textContent=d.receipts.length+' received events';let area=document.getElementById('receipts');area.replaceChildren();for(let v of d.receipts){let a=document.createElement('article'),h=document.createElement('h2'),p=document.createElement('p'),pre=document.createElement('pre');h.textContent='#'+v.payload.alert_id+' / '+v.payload.action+' / '+v.payload.severity;h.className=v.payload.action;p.textContent=v.received_at+' / '+v.delivery_key;pre.textContent=JSON.stringify(v.payload,null,2);a.append(h,p,pre);area.append(a)}}catch(e){document.getElementById('status').textContent=e.message}}document.getElementById('connect').onclick=()=>{token=document.getElementById('token').value;document.getElementById('token').value='';clearInterval(timer);refresh();timer=setInterval(refresh,5000)};</script></html>'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def reply(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        return hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + os.environ['WEBHOOK_DEMO_TOKEN'])

    def do_GET(self):
        if self.path == '/health/live':
            self.reply(200, {'status': 'ok'})
        elif self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)
        elif self.path == '/api/receipts':
            if not self.authorized():
                self.reply(401, {'error': 'Inbox credential required'})
                return
            with connection() as db:
                rows = db.execute('SELECT * FROM receipts ORDER BY id DESC LIMIT 100').fetchall()
                self.reply(200, {'receipts': [{**dict(r), 'payload': json.loads(r['payload'])} for r in rows]})
        else:
            self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        if self.path != '/webhook':
            self.reply(404, {'error': 'Not found'})
            return
        if not self.authorized():
            self.reply(401, {'error': 'Webhook credential required'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 65536:
                raise ValueError('Invalid body size')
            payload = json.loads(self.rfile.read(size))
            # Serialize duplicate deliveries before acknowledging durable commit.
            with connection() as db:
                db.execute('BEGIN IMMEDIATE')
                inserted = accept(db, self.headers.get('Idempotency-Key'), payload)
            print(json.dumps({'action': 'webhook.received', 'alert_id': payload['alert_id'],
                              'transition': payload['action'], 'inserted': inserted}), flush=True)
            self.reply(200, {'accepted': True, 'inserted': inserted})
        except (ValueError, TypeError, RecursionError):
            self.reply(400, {'error': 'Invalid event or conflicting delivery key'})
        except sqlite3.Error:
            self.reply(503, {'error': 'Storage unavailable'})


if __name__ == '__main__':
    if len(os.environ.get('WEBHOOK_DEMO_TOKEN', '')) < 24:
        raise SystemExit('Configure a private inbox token')
    with connection():
        pass
    ThreadingHTTPServer(('0.0.0.0', 8097), Handler).serve_forever()
