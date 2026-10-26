"""Prepare private runtime files without relying on the original checkout path."""
import argparse
from pathlib import Path
import secrets


def read_env(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines()
                if line and not line.lstrip().startswith('#') and '=' in line)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform-env', type=Path)
    parser.add_argument('--bind-ip', default='192.168.1.17')
    parser.add_argument('--host-id', default='tmc-lab-01')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    local = root / '.local'
    local.mkdir(exist_ok=True)
    zetaris_env = local / 'zetaris.env'
    if not zetaris_env.exists():
        if args.platform_env is None or not args.platform_env.is_file():
            parser.error('Provide --platform-env with the existing Zetaris .env, or prepare .local/zetaris.env from zetaris.env.example')
        platform = read_env(args.platform_env)
        if not platform.get('ZETARIS_ADMIN_PASSWORD'):
            parser.error('Zetaris administrator password missing in supplied file')
        zetaris_env.write_text('ZETARIS_BASE_URL=http://host.docker.internal:3000\n'
            'ZETARIS_USERNAME=' + platform.get('ZETARIS_ADMIN_EMAIL', 'admin@zetaris.com') + '\n'
            'ZETARIS_PASSWORD=' + platform['ZETARIS_ADMIN_PASSWORD'] + '\n')
    env = root / '.env'
    if not env.exists():
        env.write_text('OPENOPS_DB_PASSWORD=' + secrets.token_hex(32) + '\n'
            'OPENOPS_INGEST_TOKEN=' + secrets.token_urlsafe(32) + '\n'
            'OPENOPS_READ_TOKEN=' + secrets.token_urlsafe(32) + '\n'
            'OPENOPS_BIND_IP=' + args.bind_ip + '\nOPENOPS_HOST_ID=' + args.host_id + '\n')
    settings = read_env(env)
    for key in ('OPENOPS_ADMIN_TOKEN', 'OPENOPS_ZETARIS_DB_PASSWORD'):
        if key not in settings:
            settings[key] = secrets.token_urlsafe(32)
            with env.open('a') as stream:
                stream.write(key + '=' + settings[key] + '\n')
    destination = local / 'collector-destination.env'
    if not destination.exists():
        destination.write_text('COLLECTOR_INGEST_URL=http://' + settings['OPENOPS_BIND_IP'] + ':8096/api/ingest\n'
            'COLLECTOR_INGEST_TOKEN=' + settings['OPENOPS_INGEST_TOKEN'] + '\n')
    print('Private runtime files ready; credentials omitted. Existing files preserved.')


if __name__ == '__main__':
    main()
