"""Verify relocated preparation scripts using disposable dummy credentials only."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as folder:
    app = Path(folder)/'app'
    (app/'scripts').mkdir(parents=True)
    for name in ('prepare_receiver.py','prepare_portal.py'):
        shutil.copy2(root/'apps/openops/scripts'/name,app/'scripts'/name)
    vendor = Path(folder)/'platform.env'
    vendor.write_text('ZETARIS_ADMIN_EMAIL=example@example.invalid\nZETARIS_ADMIN_PASSWORD=dummy-test-value-only\n')
    command = [sys.executable,str(app/'scripts/prepare_receiver.py'),'--platform-env',str(vendor),'--bind-ip','192.0.2.10','--host-id','test-host']
    subprocess.run(command,check=True,capture_output=True)
    original = (app/'.env').read_bytes()
    subprocess.run(command,check=True,capture_output=True)
    assert original == (app/'.env').read_bytes(), 'Preparation changed existing credentials'
    assert '192.0.2.10:8096' in (app/'.local/collector-destination.env').read_text()
    assert 'OPENOPS_HOST_ID=test-host' in (app/'.env').read_text()
    subprocess.run([sys.executable,str(app/'scripts/prepare_portal.py')],check=True,capture_output=True)
    assert '192.0.2.10:8096' in (app/'.local/portal-access.txt').read_text()
print('PASS: preparation in a new location, configurable address/host, preserved credentials and portal note')
