"""시연용 기본 입력.

팀이 확보·검증한 공개 구조 파일에서 실제 서열을 꺼내 만든다. 서열을 이
파일에 적어 두지 않는다 — 원본이 바뀌면 같이 바뀌어야 하고, 손으로 옮기면
어느 쪽이 맞는지 알 수 없게 된다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from logic import structures
from logic.contract import SCHEMA_VERSION

TRASTUZUMAB = "1N8Z"
PERTUZUMAB = "1S78"


def _sequence(pdb_id: str, role: str) -> str:
    entities = structures.load_catalog()[pdb_id].by_role(role)
    if not entities:
        raise RuntimeError(f"{pdb_id}에 {role} 사슬이 없다. 공개 구조 파일을 확인해야 한다.")
    return entities[0].sequence


def _candidate(cid: str, name: str, heavy: str, light: str, pdb_id: str) -> dict[str, Any]:
    return {
        "candidate_id": cid,
        "name": name,
        "antibody_format": "Fab",
        "heavy_chain_fasta": f">{cid}_heavy\n{heavy}",
        "light_chain_fasta": f">{cid}_light\n{light}",
        "heavy_analysis_range": None,
        "light_analysis_range": None,
        "sources": [
            {
                "title": f"RCSB PDB {pdb_id}",
                "url": f"https://www.rcsb.org/structure/{pdb_id}",
                "record_id": pdb_id,
            }
        ],
    }


def experimental_demo() -> dict[str, Any]:
    """공개 구조가 있는 두 후보. 예측을 호출하지 않으므로 키 없이도 돈다."""
    return _review_input(
        [
            _candidate(
                "trastuzumab",
                "Trastuzumab Fab",
                _sequence(TRASTUZUMAB, "heavy"),
                _sequence(TRASTUZUMAB, "light"),
                TRASTUZUMAB,
            ),
            _candidate(
                "pertuzumab",
                "Pertuzumab Fab",
                _sequence(PERTUZUMAB, "heavy"),
                _sequence(PERTUZUMAB, "light"),
                PERTUZUMAB,
            ),
        ]
    )


def prediction_demo() -> dict[str, Any]:
    """한쪽 후보를 변이체로 바꿔 예측 경로를 타게 한다. NVIDIA 키가 필요하다.

    중쇄 한 자리만 바꾼다. 공개 구조와 정확히 일치하지 않으므로 같은 후보로
    보지 않고 Boltz-2를 호출한다. 이 변이체는 실재하는 항체가 아니라 예측
    경로를 보이기 위한 입력이다.
    """
    heavy = _sequence(PERTUZUMAB, "heavy")
    position = 30
    mutated = heavy[:position] + ("A" if heavy[position] != "A" else "G") + heavy[position + 1 :]
    return _review_input(
        [
            _candidate(
                "trastuzumab",
                "Trastuzumab Fab",
                _sequence(TRASTUZUMAB, "heavy"),
                _sequence(TRASTUZUMAB, "light"),
                TRASTUZUMAB,
            ),
            _candidate(
                "pertuzumab-variant",
                f"Pertuzumab 중쇄 {position + 1}번 변이체 (가상)",
                mutated,
                _sequence(PERTUZUMAB, "light"),
                PERTUZUMAB,
            ),
        ]
    )


def _review_input(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "example_id": None,
        "public_data_confirmed": True,
        "target": {
            "identifier": "P04626",
            "fasta": ">HER2_ECD\n" + _sequence(TRASTUZUMAB, "target"),
            "analysis_range": None,
            "sources": [
                {
                    "title": "UniProt P04626 (ERBB2)",
                    "url": "https://www.uniprot.org/uniprotkb/P04626",
                    "record_id": "P04626",
                }
            ],
        },
        "candidates": candidates,
        "uploads": [],
    }


def public_reference_demo() -> dict[str, Any]:
    """사이트의 실험 구조 비교 입력. 공개 구조에서 재생성하고 결과는 포함하지 않는다."""
    data = experimental_demo()
    data["example_id"] = "her2-public-reference-v1"
    return data


def _deposited_candidate(pdb_id: str, cid: str, name: str, heavy: str, light: str) -> dict[str, Any]:
    sequences = json.loads(Path(__file__).with_name('demo_sequences.json').read_text())[pdb_id]['entities']
    return _candidate(cid, name, sequences[heavy], sequences[light], pdb_id)


def public_prediction_demo() -> dict[str, Any]:
    """실재하는 항체 단독 구조의 기탁 서열로 HER2 복합체를 예측한다."""
    data = public_reference_demo()
    data['example_id'] = 'her2-public-prediction-v1'
    data['candidates'][1] = _deposited_candidate(
        '6BHZ', 'trastuzumab-d185a', 'Trastuzumab Fab D185A', '1', '2')
    return data


def public_hold_demo() -> dict[str, Any]:
    """예측 후보와 좌표 선택 문제로 계산이 보류되는 실제 Fab37을 함께 검토한다."""
    data = public_prediction_demo()
    data['example_id'] = 'her2-public-hold-v1'
    data['candidates'].append(_deposited_candidate('3N85', 'fab37', 'Fab37', '3', '2'))
    return data


PRESETS = {
    "public-reference": public_reference_demo,
    "public-prediction": public_prediction_demo,
    "public-hold": public_hold_demo,
    "experimental": experimental_demo,
    "prediction": prediction_demo,
}
