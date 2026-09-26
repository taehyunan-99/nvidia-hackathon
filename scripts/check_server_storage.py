"""Run inside the API container with check_server_flow's private state on stdin."""
import hashlib
import json
import os
import sys
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

state = json.load(sys.stdin)
with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row) as connection:
    row = connection.execute(
        'SELECT relative_path, sha256, size_bytes FROM uploads WHERE review_id = %s AND upload_key = %s',
        (state['review_id'], 'structure_a'),
    ).fetchone()
assert row is not None
root = Path(os.environ['SERVICE_DATA_ROOT']).resolve()
path = (root / row['relative_path']).resolve()
assert path.is_relative_to(root)
content = path.read_bytes()
assert len(content) == row['size_bytes']
assert hashlib.sha256(content).hexdigest() == row['sha256'] == state['upload_sha256']
print('Database reference and restored upload bytes: PASS')
