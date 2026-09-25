"""`.env` 관리와 비밀값 노출 방지 검증."""

from __future__ import annotations

import subprocess

import pytest

from logic import env
from logic.contract import REPO_ROOT

FAKE = "nvapi-" + "x" * 58


def test_parse_env_ignores_comments_and_blanks():
    parsed = env.parse_env(
        "\n".join(
            [
                "# 주석",
                "",
                "NVIDIA_API_KEY=abc123",
                "  NEMOTRON_MODEL = nemotron-x  ",
                "형식이_아닌_줄",
            ]
        )
    )
    assert parsed == {"NVIDIA_API_KEY": "abc123", "NEMOTRON_MODEL": "nemotron-x"}


def test_parse_env_strips_quotes():
    assert env.parse_env('NVIDIA_API_KEY="abc"')["NVIDIA_API_KEY"] == "abc"
    assert env.parse_env("NVIDIA_API_KEY='abc'")["NVIDIA_API_KEY"] == "abc"


def test_load_env_does_not_override_existing_environment(tmp_path, monkeypatch):
    """이미 있는 환경변수를 .env가 조용히 덮으면 어느 키를 썼는지 알 수 없다."""
    path = tmp_path / ".env"
    path.write_text("NVIDIA_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("NVIDIA_API_KEY", "from-shell")

    applied = env.load_env(path)

    assert applied == []
    assert env.os.environ["NVIDIA_API_KEY"] == "from-shell"


def test_load_env_can_override_when_asked(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("NVIDIA_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("NVIDIA_API_KEY", "from-shell")

    env.load_env(path, override=True)

    assert env.os.environ["NVIDIA_API_KEY"] == "from-file"


def test_load_env_skips_empty_values(tmp_path, monkeypatch):
    """값을 비워 둔 .env.example을 복사만 했을 때 빈 문자열이 키로 잡히면 안 된다."""
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text("NVIDIA_API_KEY=\n", encoding="utf-8")

    assert env.load_env(path) == []
    assert not env.os.getenv("NVIDIA_API_KEY")


def test_load_env_returns_names_not_values(tmp_path, monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text(f"NVIDIA_API_KEY={FAKE}\n", encoding="utf-8")

    applied = env.load_env(path)

    assert applied == ["NVIDIA_API_KEY"]
    assert FAKE not in " ".join(applied)


@pytest.mark.parametrize("secret", [FAKE, "short", "nvapi-abcdefghijkl"])
def test_mask_never_reveals_whole_secret(secret):
    masked = env.mask(secret)
    assert secret not in masked
    assert len(masked) < len(secret) + 20


def test_mask_handles_empty():
    assert env.mask("") == "(없음)"


def test_describe_key_does_not_print_the_key(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", FAKE)
    monkeypatch.setattr(env, "ENV_PATH", REPO_ROOT / "does-not-exist.env")

    described = env.describe_key()

    assert FAKE not in described
    assert "NVIDIA_API_KEY" in described
    assert "형식 확인" in described


def test_describe_key_warns_on_unexpected_prefix(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "sk-wrong-provider-key")
    monkeypatch.setattr(env, "ENV_PATH", REPO_ROOT / "does-not-exist.env")

    assert "경고" in env.describe_key()


def test_describe_key_reports_absence(monkeypatch):
    for name in env.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env, "ENV_PATH", REPO_ROOT / "does-not-exist.env")

    described = env.describe_key()

    assert "키 없음" in described
    assert "build.nvidia.com/settings/api-keys" in described


# ---------------------------------------------------------------- 저장소 보호
def test_git_ignores_dotenv_but_keeps_example():
    """.env가 실수로 커밋되지 않는지 git에게 직접 묻는다."""
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT
    ).returncode
    tracked_example = subprocess.run(
        ["git", "check-ignore", "-q", ".env.example"], cwd=REPO_ROOT
    ).returncode

    assert ignored == 0, ".env가 .gitignore에 걸리지 않는다"
    assert tracked_example == 1, ".env.example까지 무시되면 팀에 공유되지 않는다"


def test_example_file_has_no_real_key():
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("NVIDIA_API_KEY="):
            assert line.strip() == "NVIDIA_API_KEY=", "예제 파일에 값이 들어 있다"
    assert env.KEY_PREFIX not in text.replace("nvapi- 로 시작한다", "")
