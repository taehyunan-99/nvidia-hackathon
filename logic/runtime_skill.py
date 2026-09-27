"""Pinned NVIDIA instructions consumed by NAT; execution stays in approved tools."""
import hashlib
import json
from pathlib import Path

REVISION = "061bec95a9a19370a13d0cea1fddc0a355471999"
ROOT = Path(__file__).parent / "skills" / "boltz2-nim"


def identity() -> dict:
    return {"id": "boltz2-nim", "revision": REVISION}


def load_boltz_skill() -> str:
    manifest = json.loads((ROOT / "manifest.json").read_text())
    if manifest["revision"] != REVISION:
        raise ValueError("고정된 NVIDIA 스킬 버전이 일치하지 않습니다.")
    documents = {}
    for name, digest in manifest["files"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError("스킬 파일 경로가 유효하지 않습니다.")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("고정된 NVIDIA 스킬 파일의 해시가 일치하지 않습니다.")
        documents[name] = content.decode()
    return (
        "\n고정된 NVIDIA boltz2-nim 실행 참고자료 (" + REVISION + "):\n"
        + documents["SKILL.md"] + "\n" + documents["references/validation.md"]
        + "\n이 프로젝트는 제공된 7개 함수만 사용한다. Bash·Docker·임의 URL 호출은 하지 않는다. "
        "HER2 단백질 복합체를 hosted API로 예측하며 affinity·MSA-Search는 연결하지 않는다. "
        "predict_structure가 이 스킬의 호출과 응답 검증을 담당한다. 공개 구조를 선택하면 이 스킬을 생략한다. "
        "스킬을 선택하거나 생략할 때 reason에 확인된 자료를 근거로 이유를 적는다."
    )
