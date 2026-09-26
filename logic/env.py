"""로컬 `.env` 로딩과 자격 증명 확인.

CONTRIBUTING의 "비밀키는 로컬 환경변수나 추후 CI secret으로 전달한다"를 따른다.
`.env`는 .gitignore가 막고 있으며 `.env.example`에는 실제 값을 넣지 않는다.

이 모듈은 키 값을 절대 출력하지 않는다. 진단이 필요하면 mask()로 앞뒤 일부만 남긴다.
"""

from __future__ import annotations

import os
from pathlib import Path

from .contract import REPO_ROOT

ENV_PATH = REPO_ROOT / ".env"
KEY_NAMES = ("NVIDIA_API_KEY", "NGC_API_KEY")

# build.nvidia.com이 발급하는 키의 접두사. 형식 확인에만 쓴다.
KEY_PREFIX = "nvapi-"


def parse_env(text: str) -> dict[str, str]:
    """KEY=VALUE 줄만 읽는다. 주석과 빈 줄은 건너뛴다."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        value = value.strip()
        # 따옴표로 감싼 값을 허용한다.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_env(path: Path | None = None, *, override: bool = False) -> list[str]:
    """`.env`를 os.environ에 올린다. 이미 있는 환경변수는 기본적으로 두 번 덮지 않는다.

    돌려주는 값은 설정된 이름 목록이며 값은 담지 않는다.
    """
    target = path if path is not None else ENV_PATH
    if not target.exists():
        return []
    applied = []
    for key, value in parse_env(target.read_text(encoding="utf-8")).items():
        if not value:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
            applied.append(key)
    return applied


def mask(secret: str) -> str:
    """로그·화면에 쓸 수 있는 형태. 전체 값을 복원할 수 없어야 한다."""
    if not secret:
        return "(없음)"
    if len(secret) <= 12:
        return f"{secret[:2]}…({len(secret)}자)"
    return f"{secret[:8]}…{secret[-4:]} ({len(secret)}자)"


def find_key() -> tuple[str | None, str | None]:
    """(키, 어느 이름에서 왔는지). `.env`를 먼저 올린 뒤 찾는다."""
    load_env()
    for name in KEY_NAMES:
        value = os.getenv(name)
        if value:
            return value, name
    return None, None


def describe_key() -> str:
    """키 상태를 사람이 읽을 수 있게. 값 자체는 나오지 않는다."""
    key, name = find_key()
    if not key:
        return (
            f"키 없음. {ENV_PATH}에 NVIDIA_API_KEY를 넣어야 한다. "
            f"발급: https://build.nvidia.com/settings/api-keys"
        )
    shape = "형식 확인" if key.startswith(KEY_PREFIX) else f"경고: '{KEY_PREFIX}'로 시작하지 않음"
    return f"{name} = {mask(key)} · {shape}"
