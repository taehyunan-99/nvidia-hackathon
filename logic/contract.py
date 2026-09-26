"""임시 계약 v0.1.0 로딩과 검증.

필드 정의 원본은 docs/frontend-hosting/contracts/service.schema.json이다.
이 모듈은 그 스키마를 읽기만 하며 자체 사본을 두지 않는다. 계약이 바뀌면
여기서 따로 고칠 것이 없고, 검증이 실패해 변경 사실이 드러나야 한다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_VERSION = "0.1.0"

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "docs" / "frontend-hosting" / "contracts" / "service.schema.json"


class ContractError(ValueError):
    """생산한 객체가 임시 계약과 맞지 않을 때."""


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _validator(def_name: str) -> Draft202012Validator:
    schema = load_schema()
    if def_name not in schema["$defs"]:
        raise KeyError(f"스키마에 없는 자료형: {def_name}")
    # $ref가 형제 $defs를 찾을 수 있도록 루트 스키마를 함께 넘긴다.
    sub = {"$ref": f"#/$defs/{def_name}", "$defs": schema["$defs"]}
    return Draft202012Validator(sub)


def validate(obj: Any, def_name: str) -> None:
    """맞지 않으면 ContractError를 낸다. 맞으면 아무것도 하지 않는다."""
    errors = sorted(_validator(def_name).iter_errors(obj), key=lambda e: list(e.path))
    if errors:
        lines = [f"{def_name} 계약 위반 {len(errors)}건:"]
        for e in errors[:10]:
            where = "/".join(str(p) for p in e.path) or "(최상위)"
            lines.append(f"  - {where}: {e.message}")
        raise ContractError("\n".join(lines))


def is_valid(obj: Any, def_name: str) -> bool:
    return _validator(def_name).is_valid(obj)


def now_rfc3339() -> str:
    """UTC RFC 3339. 계약의 시각 표기는 전부 이 형식이다."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
