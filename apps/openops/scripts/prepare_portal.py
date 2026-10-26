"""Create a private local operator-access note; never print its credential."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
settings = dict(line.split('=',1) for line in (root/'.env').read_text().splitlines() if line and not line.startswith('#'))
path = root/'.local/portal-access.txt'
path.write_text('OpenOps operator access (private; do not share in chat)\n\n'
                'URL: http://' + settings.get('OPENOPS_BIND_IP','192.168.1.17') + ':8096\n\n'
                'Paste this operator token into the dashboard, then click Connect:\n'
                + settings['OPENOPS_ADMIN_TOKEN']+'\n')
print('Private portal access note created; token omitted.')
