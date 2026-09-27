"""Check the CloudFront-origin Compose configuration without printing secrets or creating AWS resources."""
import argparse
import json
import re
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--env-file', default='.env.aws.local')
args = parser.parse_args()
assert Path(args.env_file).stat().st_mode & 0o077 == 0, 'The private env file must have mode 600'
config = json.loads(subprocess.check_output([
    'docker', 'compose', '--env-file', args.env_file, '-f', 'compose.server.yaml', '-f', 'compose.aws.yaml', 'config', '--format', 'json'
], text=True))
services = config['services']
assert re.fullmatch(r'[a-f0-9]{48,}', services['db']['environment']['POSTGRES_PASSWORD']), 'Use a random hex DB password'
web = services['web']
host = web['environment']['SITE_ADDRESS']
assert re.fullmatch(r'd[a-z0-9]+\.cloudfront\.net', host), 'Use the actual CloudFront hostname'
assert re.fullmatch(r'[a-f0-9]{64}', web['environment']['ORIGIN_VERIFY_SECRET']), 'Use a random 64-character hex origin secret'
assert web['environment']['PUBLIC_ORIGIN'] == 'https://' + host
for name in ['api', 'worker', 'migrate']:
    service = services[name]
    env = service['environment']
    assert env['ALLOWED_ORIGINS'] == 'https://' + host and env['SECURE_COOKIE'] == 'true'
    assert env['DATA_MODE'] in {'mock', 'live'}
    assert not service.get('ports'), 'Only the CloudFront origin may publish a port'
    assert re.fullmatch(r'(sha256:[a-f0-9]{64}|\S+@sha256:[a-f0-9]{64})', service['image']), 'Pin API images by immutable ID or digest'
assert len({services[n]['environment']['DATA_MODE'] for n in ['api', 'worker', 'migrate']}) == 1
assert not services['db'].get('ports'), 'The DB must not publish a port'
assert re.fullmatch(r'(sha256:[a-f0-9]{64}|\S+@sha256:[a-f0-9]{64})', web['image']), 'Pin the web image by immutable ID or digest'
assert len(web['ports']) == 1 and web['ports'][0]['target'] == 80 and int(web['ports'][0]['published']) == 80
assert web['ports'][0]['host_ip'] == '0.0.0.0'
assert any(v['target'] == '/etc/caddy/Caddyfile' and Path(v['source']).name == 'Caddyfile.aws' and v.get('read_only') for v in web['volumes'])
worker = services['worker']['environment']
assert not worker.get('MODEL_BUDGET_PATH'), 'Public operation uses per-run budgets; never reset or reuse a test aggregate budget'
assert int(worker['NEMOTRON_REQUEST_LIMIT']) == 40, 'Keep the existing per-run model limit'
assert worker['MODEL_DAILY_BUDGET_PATH'] == '/data/model-daily-budget.sqlite3'
assert all(int(worker[key]) > 0 for key in ['NEMOTRON_DAILY_REQUEST_LIMIT', 'BOLTZ2_DAILY_REQUEST_LIMIT'])
assert worker['PDB_SEARCH_ENABLED'] in {'0', '1'}
if worker['DATA_MODE'] == 'live':
    assert worker.get('NVIDIA_API_KEY'), 'Live operation requires the private NVIDIA key'
for key in ['MAX_SESSION_RUNS', 'MAX_ACTIVE_RUNS', 'ANALYSIS_TIMEOUT_SECONDS', 'MAX_SESSIONS', 'MAX_SESSION_REVIEWS', 'MAX_STORAGE_BYTES', 'MAX_REQUEST_BYTES', 'REQUESTS_PER_MINUTE']:
    assert int(worker[key]) > 0 and worker[key] == services['api']['environment'][key]
assert int(worker['MAX_SESSION_RUNS']) == 1 and int(worker['MAX_ACTIVE_RUNS']) <= 10
assert sum(int(s['mem_limit']) for s in services.values()) <= 3584 * 1024**2
print('AWS Compose configuration: PASS. AWS firewall, IAM, TLS, architecture and origin behavior still require remote verification.')
