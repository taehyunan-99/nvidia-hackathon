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


def test_public_daily_budget_allows_more_than_four_runs(tmp_path, monkeypatch):
    monkeypatch.setenv('MODEL_DAILY_BUDGET_PATH', str(tmp_path / 'daily.sqlite3'))
    for index in range(5):
        reserve('boltz2', tmp_path / f'run-{index}')
    with sqlite3.connect(tmp_path / 'daily.sqlite3') as conn:
        assert conn.execute("SELECT used FROM daily_requests WHERE kind='boltz2'").fetchone()[0] == 5


def test_daily_budget_is_atomic_across_different_runs(tmp_path, monkeypatch):
    monkeypatch.setenv('MODEL_DAILY_BUDGET_PATH', str(tmp_path / 'daily.sqlite3'))
    monkeypatch.setenv('BOLTZ2_DAILY_REQUEST_LIMIT', '3')
    def send(index):
        try:
            reserve('boltz2', tmp_path / f'run-{index}')
            return True
        except CallFailed:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(send, range(12))) == 3
    with sqlite3.connect(tmp_path / 'daily.sqlite3') as conn:
        assert conn.execute('SELECT used FROM daily_requests').fetchone()[0] == 3
    total = 0
    for path in tmp_path.glob('run-*/request-budget.sqlite3'):
        with sqlite3.connect(path) as conn:
            total += conn.execute('SELECT COALESCE(SUM(used), 0) FROM requests').fetchone()[0]
    assert total == 3  # A rejected daily reservation must not spend a run's allowance.


def test_daily_limits_are_separate_and_changes_preserve_usage(tmp_path, monkeypatch):
    import pytest
    path = tmp_path / 'daily.sqlite3'
    monkeypatch.setenv('MODEL_DAILY_BUDGET_PATH', str(path))
    monkeypatch.setenv('NEMOTRON_DAILY_REQUEST_LIMIT', '1')
    monkeypatch.setenv('BOLTZ2_DAILY_REQUEST_LIMIT', '2')
    reserve('nemotron', tmp_path / 'one')
    with pytest.raises(CallFailed, match='일일'):
        reserve('nemotron', tmp_path / 'two')
    reserve('boltz2', tmp_path / 'two')
    reserve('boltz2', tmp_path / 'three')
    with pytest.raises(CallFailed, match='일일'):
        reserve('boltz2', tmp_path / 'four')
    monkeypatch.setenv('BOLTZ2_DAILY_REQUEST_LIMIT', '3')
    reserve('boltz2', tmp_path / 'four')
    with pytest.raises(CallFailed, match='일일'):
        reserve('boltz2', tmp_path / 'five')


def test_new_day_restores_daily_allowance_without_resetting_run_or_audit(tmp_path, monkeypatch):
    import pytest
    from logic import call_budget
    monkeypatch.setenv('MODEL_DAILY_BUDGET_PATH', str(tmp_path / 'daily.sqlite3'))
    monkeypatch.setenv('BOLTZ2_DAILY_REQUEST_LIMIT', '4')
    monkeypatch.setattr(call_budget, '_budget_day', lambda: '2026-09-27')
    for _ in range(4):
        reserve('boltz2', tmp_path / 'first')
    monkeypatch.setattr(call_budget, '_budget_day', lambda: '2026-09-28')
    with pytest.raises(CallFailed, match='4'):
        reserve('boltz2', tmp_path / 'first')
    reserve('boltz2', tmp_path / 'second')
    with sqlite3.connect(tmp_path / 'daily.sqlite3') as conn:
        assert conn.execute('SELECT day, used FROM daily_requests ORDER BY day').fetchall() == [('2026-09-27', 4), ('2026-09-28', 1)]


def test_daily_budget_cannot_share_the_run_budget_file(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setenv('MODEL_DAILY_BUDGET_PATH', str(tmp_path / 'request-budget.sqlite3'))
    with pytest.raises(CallFailed, match='다른 파일'):
        reserve('boltz2', tmp_path)


def test_daily_window_changes_at_korean_midnight(monkeypatch):
    from datetime import datetime, timezone
    from logic import call_budget
    class Clock:
        instant = datetime(2026, 9, 27, 14, 59, 59, tzinfo=timezone.utc)
        @classmethod
        def now(cls, tz):
            return cls.instant.astimezone(tz)
    monkeypatch.setattr(call_budget, 'datetime', Clock)
    assert call_budget._budget_day() == '2026-09-27'
    Clock.instant = datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)
    assert call_budget._budget_day() == '2026-09-28'
