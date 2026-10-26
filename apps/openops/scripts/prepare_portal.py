"""Export the initial administrator note after receiver readiness."""
from pathlib import Path
import os
import shutil
import subprocess
import time
import urllib.request

root = Path(__file__).resolve().parents[1]
settings = dict(line.split('=', 1) for line in (root / '.env').read_text(encoding='utf-8-sig').splitlines()
                if line and not line.startswith('#') and '=' in line)
docker = shutil.which('docker') or str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Docker/Docker/resources/bin/docker.exe')
base = 'http://' + settings.get('OPENOPS_BIND_IP', '192.168.1.17') + ':8096'
for attempt in range(30):
    try:
        with urllib.request.urlopen(base + '/health/ready', timeout=2):
            break
    except OSError:
        if attempt == 29:
            raise SystemExit('Receiver is not ready. Start Docker Compose first.')
        time.sleep(1)
local = root / '.local'
local.mkdir(exist_ok=True)
subprocess.run([docker, 'compose', 'cp', 'receiver:/app/logs/bootstrap-admin.txt', str(local / 'admin-access.txt')],
               cwd=root, check=True, stdout=subprocess.DEVNULL)
print('Initial administrator note saved to .local/admin-access.txt; password omitted. Valid only before changing the initial password.')
