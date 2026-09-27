"""Reserve physical provider requests before sending, including retries."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3


def _budget_day() -> str:
    return datetime.now(timezone(timedelta(hours=9))).date().isoformat()


def reserve(kind: str, work_dir: Path) -> None:
    from .nvidia_client import CallFailed

    limits = {'nemotron': int(os.getenv('NEMOTRON_REQUEST_LIMIT', '40')), 'boltz2': 4}
    if limits['nemotron'] < 1:
        raise CallFailed('Nemotron 요청 상한은 양수여야 한다.')
    path = Path(os.getenv('MODEL_BUDGET_PATH') or work_dir / 'request-budget.sqlite3')
    path.parent.mkdir(parents=True, exist_ok=True)
    daily_path = os.getenv('MODEL_DAILY_BUDGET_PATH')
    if daily_path:
        daily_path = Path(daily_path)
        if daily_path.resolve() == path.resolve():
            raise CallFailed('일일 한도와 실행 한도는 다른 파일에 저장해야 한다.')
        daily_path.parent.mkdir(parents=True, exist_ok=True)
        daily_limit = int(os.getenv(f'{kind.upper()}_DAILY_REQUEST_LIMIT', '4000' if kind == 'nemotron' else '200'))
        if daily_limit < 1:
            raise CallFailed('일일 요청 상한은 양수여야 한다.')
    with sqlite3.connect(path, timeout=10) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS requests (kind TEXT PRIMARY KEY, used INTEGER NOT NULL)')
        if daily_path:
            conn.execute('ATTACH DATABASE ? AS daily', (str(daily_path),))
            conn.execute('CREATE TABLE IF NOT EXISTS daily.daily_requests (day TEXT, kind TEXT, used INTEGER NOT NULL, PRIMARY KEY(day, kind))')
        # Reserve the per-run and shared daily counters in the same SQLite transaction.
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT used FROM requests WHERE kind=?', (kind,)).fetchone()
        used = row[0] if row else 0
        if used >= limits[kind]:
            raise CallFailed(f'{kind} 실제 요청 상한 {limits[kind]}건에 도달해 호출하지 않았다.')
        if daily_path:
            day = _budget_day()
            row = conn.execute('SELECT used FROM daily.daily_requests WHERE day=? AND kind=?', (day, kind)).fetchone()
            if row and row[0] >= daily_limit:
                raise CallFailed(f'{kind} 일일 요청 상한 {daily_limit}건에 도달해 호출하지 않았다. 한국시간 자정 이후 다시 시도한다.')
            conn.execute('INSERT INTO daily.daily_requests VALUES (?, ?, 1) ON CONFLICT(day, kind) DO UPDATE SET used=used+1', (day, kind))
        conn.execute('INSERT INTO requests VALUES (?, 1) ON CONFLICT(kind) DO UPDATE SET used=used+1', (kind,))
