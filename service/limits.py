"""Local admission limits shared by the persistent API and worker."""
import json
import asyncio
import time
from pathlib import Path

from .db import connect


def storage_bytes(root: Path, dsn: str | None = None) -> int:
    total = 0
    for path in root.rglob('*'):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except FileNotFoundError:
            pass  # Concurrent cleanup can remove a file between listing and stat.
    if dsn:
        with connect(dsn) as conn:
            total += conn.execute("SELECT pg_database_size(current_database()) AS size").fetchone()["size"]
    return total


def admit_request(dsn: str, limit: int) -> bool:
    with connect(dsn) as conn:
        row = conn.execute(
            "INSERT INTO request_budget(bucket, used) VALUES (date_trunc('minute', now()), 1) "
            "ON CONFLICT (bucket) DO UPDATE SET used = request_budget.used + 1 "
            "WHERE request_budget.used < %s RETURNING used", (limit,),
        ).fetchone()
        conn.execute("DELETE FROM request_budget WHERE bucket < date_trunc('minute', now())")
    return row is not None


class IntakeLimit:
    """Bound modifying request bytes before multipart parsing (including chunked bodies)."""
    def __init__(self, app, *, dsn, mode, max_bytes, requests_per_minute):
        self.app, self.dsn, self.mode = app, dsn, mode
        self.max_bytes, self.requests_per_minute = max_bytes, requests_per_minute
        self.receiving = False

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            return await self.app(scope, receive, send)
        from starlette.concurrency import run_in_threadpool
        if not await run_in_threadpool(admit_request, self.dsn, self.requests_per_minute):
            return await self.reject(send, 429, 'REQUEST_LIMIT_REACHED', '요청이 많습니다. 잠시 뒤 다시 시도하세요.')
        length = dict(scope['headers']).get(b'content-length')
        if length and (not length.isdigit() or int(length) > self.max_bytes):
            return await self.reject(send, 413, 'INPUT_TOO_LARGE', '요청 크기 제한을 넘었습니다.')
        if self.receiving:
            return await self.reject(send, 429, 'INTAKE_BUSY', '다른 입력을 수신 중입니다. 잠시 뒤 다시 시도하세요.')
        self.receiving = True
        try:
            return await self.read_body(scope, receive, send)
        finally:
            self.receiving = False

    async def read_body(self, scope, receive, send):
        chunks, size = [], 0
        deadline = time.monotonic() + 30
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return await self.reject(send, 408, 'REQUEST_TIMEOUT', '입력 수신 제한 시간을 넘었습니다.')
            try:
                message = await asyncio.wait_for(receive(), timeout=remaining)
            except TimeoutError:
                return await self.reject(send, 408, 'REQUEST_TIMEOUT', '입력 수신 제한 시간을 넘었습니다.')
            if message['type'] == 'http.disconnect':
                return
            body = message.get('body', b'')
            size += len(body)
            if size > self.max_bytes:
                return await self.reject(send, 413, 'INPUT_TOO_LARGE', '요청 크기 제한을 넘었습니다.')
            chunks.append(body)
            if not message.get('more_body', False):
                break
        body = b''.join(chunks)
        delivered = False
        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        await self.app(scope, replay, send)

    async def reject(self, send, status, code, message):
        body = json.dumps({'schema_version': '0.1.0', 'data_mode': self.mode, 'code': code,
            'message': message, 'run_id': None, 'candidate_id': None, 'step_id': None,
            'field_errors': [], 'retry_action': 'none'}).encode()
        await send({'type': 'http.response.start', 'status': status,
                    'headers': [(b'content-type', b'application/json'), (b'cache-control', b'no-store')]})
        await send({'type': 'http.response.body', 'body': body})
