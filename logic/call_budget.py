"""Reserve physical provider requests before sending, including retries."""
import os
from pathlib import Path
import sqlite3


def reserve(kind: str, work_dir: Path) -> None:
    from .nvidia_client import CallFailed

    limits = {'nemotron': int(os.getenv('NEMOTRON_REQUEST_LIMIT', '40')), 'boltz2': 4}
    if limits['nemotron'] < 1:
        raise CallFailed('Nemotron 요청 상한은 양수여야 한다.')
    path = Path(os.getenv('MODEL_BUDGET_PATH') or work_dir / 'request-budget.sqlite3')
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=10) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS requests (kind TEXT PRIMARY KEY, used INTEGER NOT NULL)')
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT used FROM requests WHERE kind=?', (kind,)).fetchone()
        used = row[0] if row else 0
        if used >= limits[kind]:
            raise CallFailed(f'{kind} 실제 요청 상한 {limits[kind]}건에 도달해 호출하지 않았다.')
        conn.execute('INSERT INTO requests VALUES (?, 1) ON CONFLICT(kind) DO UPDATE SET used=used+1', (kind,))
