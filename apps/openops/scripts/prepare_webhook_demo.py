"""Create the private local inbox credential once; preserve existing values."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
local = root / '.local'
local.mkdir(exist_ok=True)
path = local / 'webhook-demo.env'
if not path.exists():
    path.write_text('WEBHOOK_DEMO_TOKEN=' + secrets.token_urlsafe(40) + '\n', encoding='utf-8')
settings = dict(line.split('=', 1) for line in path.read_text(encoding='utf-8').splitlines() if '=' in line)
(local / 'webhook-inbox-access.txt').write_text(
    'OpenOps local webhook inbox\nURL: http://127.0.0.1:8097\nToken: ' + settings['WEBHOOK_DEMO_TOKEN'] + '\n', encoding='utf-8')
print('Local webhook inbox settings ready; credential omitted.')
