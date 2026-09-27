from concurrent.futures import ThreadPoolExecutor
import sqlite3

from logic.call_budget import reserve
from logic.nvidia_client import CallFailed


def test_concurrent_requests_cannot_exceed_the_shared_cap(tmp_path, monkeypatch):
    path = tmp_path / 'budget.sqlite3'
    monkeypatch.setenv('MODEL_BUDGET_PATH', str(path))
    def send(_):
        try:
            reserve('boltz2', tmp_path)
            return True
        except CallFailed:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(send, range(12))) == 4
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT used FROM requests').fetchone()[0] == 4
    assert send(None) is False


def test_chat_and_prediction_have_separate_limits(tmp_path):
    for _ in range(4):
        reserve('boltz2', tmp_path)
    reserve('nemotron', tmp_path)


def test_explicit_limit_change_preserves_already_spent_requests(tmp_path, monkeypatch):
    for _ in range(36):
        reserve('nemotron', tmp_path)
    monkeypatch.setenv('NEMOTRON_REQUEST_LIMIT', '52')
    for _ in range(16):
        reserve('nemotron', tmp_path)
    import pytest
    with pytest.raises(CallFailed, match='52'):
        reserve('nemotron', tmp_path)
