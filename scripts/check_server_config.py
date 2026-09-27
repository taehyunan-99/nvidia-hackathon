"""Validate the server rehearsal without printing resolved secrets or creating resources."""
import argparse
import json
import re
import subprocess
from urllib.parse import urlsplit

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--env-file', default='.env.server.local')
args = parser.parse_args()
config = json.loads(subprocess.check_output([
    'docker', 'compose', '--env-file', args.env_file, '-f', 'compose.server.yaml', 'config', '--format', 'json'
], text=True))
services = config['services']
password = services['db']['environment']['POSTGRES_PASSWORD']
assert re.fullmatch(r'[a-fA-F0-9]{32,}', password), 'Use a random hex DB password of at least 32 characters'
host = services['web']['environment']['SITE_ADDRESS']
assert re.fullmatch(r'[a-zA-Z0-9.-]+', host), 'SITE_ADDRESS must be a hostname without scheme or port'
for name in ['migrate', 'api', 'worker']:
    env = services[name]['environment']
    origin = urlsplit(env['ALLOWED_ORIGINS'])
    assert origin.scheme == 'https' and origin.hostname == host, 'HTTPS origin and site hostname must match'
    assert not origin.path and not origin.query and not origin.fragment and not origin.username
    assert env['SECURE_COOKIE'] == 'true' and env['DATA_MODE'] in {'mock', 'live'}
assert len({services[name]['environment']['DATA_MODE'] for name in ['migrate', 'api', 'worker']}) == 1
for key in ['MAX_SESSION_RUNS', 'MAX_ACTIVE_RUNS', 'ANALYSIS_TIMEOUT_SECONDS', 'MAX_SESSIONS', 'MAX_SESSION_REVIEWS', 'MAX_STORAGE_BYTES', 'MAX_REQUEST_BYTES', 'REQUESTS_PER_MINUTE']:
    assert all(int(services[name]['environment'][key]) > 0 for name in ['api', 'worker'])
    assert services['api']['environment'][key] == services['worker']['environment'][key]
assert services['worker']['environment']['PDB_SEARCH_ENABLED'] in {'0', '1'}
for name in ['db', 'api', 'worker']:
    assert not services[name].get('ports'), f'{name} must not publish a port'
for port in services['web']['ports']:
    assert port['host_ip'] == '127.0.0.1', 'Public exposure remains blocked until analysis/admission integration'
https_port = next(int(p['published']) for p in services['web']['ports'] if p['target'] == 443)
assert (origin.port or 443) == https_port, 'HTTPS port and browser origin must match'
assert sum(int(s['mem_limit']) for s in services.values()) <= 3584 * 1024**2
print('Server rehearsal configuration: PASS (loopback only, HTTPS, private DB, bounded memory)')
