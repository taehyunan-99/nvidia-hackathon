"""Create or re-read a private mock run over verified HTTPS; use disposable stacks."""
import argparse
import hashlib
import json
import os
import ssl
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('mode', choices=['create', 'verify'])
parser.add_argument('--base-url', default='https://localhost:8443')
parser.add_argument('--ca', type=Path, required=True)
parser.add_argument('--state', type=Path, required=True, help='Private local checkpoint; keep outside Git')
args = parser.parse_args()
assert args.base_url.startswith('https://'), 'HTTPS is required'
context = ssl.create_default_context(cafile=str(args.ca))
jar = CookieJar()
opener = build_opener(HTTPSHandler(context=context), HTTPCookieProcessor(jar))
checkpoint = {} if args.mode == 'create' else json.loads(args.state.read_text())


def request(path, body=None, content_type='application/json', *, anonymous=False):
    headers = {'Origin': args.base_url}
    if body is not None:
        headers['Content-Type'] = content_type
    if checkpoint and not anonymous:
        headers['Cookie'] = checkpoint['cookie']
    client = build_opener(HTTPSHandler(context=context)) if anonymous else opener
    with client.open(Request(args.base_url + path, data=body, headers=headers), timeout=15) as response:
        return json.load(response), response.headers


if args.mode == 'create':
    assert not args.state.exists(), 'Use a new state path; do not overwrite existing checkpoints'
    session, headers = request('/api/session', b'')
    cookie = headers['Set-Cookie']
    assert session['status'] == 'active' and 'Secure' in cookie and 'HttpOnly' in cookie
    payload = json.loads(Path('docs/frontend-hosting/fixtures/scenarios.json').read_text())['input']
    source = Path('frontend/public/structures/1N8Z.cif').read_bytes()
    payload['uploads'] = [{'upload_key': 'structure_a', 'file_name': '1N8Z.cif', 'format': 'mmcif',
        'candidate_id': payload['candidates'][0]['candidate_id'], 'role': 'complex',
        'source': {'title': 'PDB 1N8Z', 'url': 'https://www.rcsb.org/structure/1N8Z', 'record_id': '1N8Z'}}]
    boundary = 'her2-server-check-boundary'
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n{json.dumps(payload)}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="structure_a"; filename="1N8Z.cif"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n').encode() + source + f'\r\n--{boundary}--\r\n'.encode()
    review, _ = request('/api/reviews', body, f'multipart/form-data; boundary={boundary}')
    run, _ = request(f"/api/reviews/{review['review_id']}/runs", b'{"request_key":"server-check"}')
    for _ in range(60):
        current, _ = request(f"/api/runs/{run['run_id']}")
        if current['result_available']:
            break
        time.sleep(1)
    else:
        raise AssertionError('mock worker did not finish')
    checkpoint = {'review_id': review['review_id'], 'run_id': run['run_id'],
                  'cookie': cookie.split(';', 1)[0], 'upload_sha256': hashlib.sha256(source).hexdigest()}
    # Restrict the file before writing the session cookie.
    with os.fdopen(os.open(args.state, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as file:
        json.dump(checkpoint, file)

review, _ = request(f"/api/reviews/{checkpoint['review_id']}")
assert review['uploads'][0]['upload_key'] == 'structure_a'
result, _ = request(f"/api/runs/{checkpoint['run_id']}/result")
assert result['run_id'] == checkpoint['run_id'] and result['data_mode'] == 'mock'
for path in [f"/api/reviews/{checkpoint['review_id']}", f"/api/runs/{checkpoint['run_id']}/result"]:
    try:
        request(path, anonymous=True)
    except HTTPError as error:
        assert error.code == 401, error.code
    else:
        raise AssertionError('anonymous access was allowed')
for artifact in result['artifacts']:
    assert artifact['status'] != 'ready'
print('HTTPS, Secure cookie, saved review/result and anonymous isolation: PASS')
