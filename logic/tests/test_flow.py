"""판단 흐름의 분기별 검증.

실제 서열은 팀이 확보한 공개 구조 파일에서 꺼내 쓴다. 기대값을 구현 결과에서
만들어내지 않도록, 접촉 잔기 수는 contacts.json을 직접 읽어 대조한다.
NVIDIA 호출이 필요한 분기는 응답을 흉내 낸 대역 client로 확인하며,
이것으로 실제 호출을 검증했다고 보지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from logic import structures
from logic.contract import SCHEMA_VERSION, validate
from logic.flow import Flow, run_flow
from logic.nvidia_client import CallFailed, MissingCredentials

TRASTUZUMAB = "1N8Z"
PERTUZUMAB = "1S78"


def entity_sequence(pdb_id: str, role: str) -> str:
    structure = structures.load_catalog()[pdb_id]
    entities = structure.by_role(role)
    assert entities, f"{pdb_id}에 {role} 사슬이 없다"
    return entities[0].sequence


def candidate(cid: str, name: str, heavy: str, light: str) -> dict:
    return {
        "candidate_id": cid,
        "name": name,
        "antibody_format": "Fab",
        "heavy_chain_fasta": f">{cid}_heavy\n{heavy}",
        "light_chain_fasta": f">{cid}_light\n{light}",
        "heavy_analysis_range": None,
        "light_analysis_range": None,
        "sources": [],
    }


def make_request(candidates: list[dict], work_dir: Path, *, target_fasta: str | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": "run-test",
        "review_id": "rev-test",
        "input": {
            "schema_version": SCHEMA_VERSION,
            "example_id": None,
            "public_data_confirmed": True,
            "target": {
                "identifier": "P04626",
                "fasta": target_fasta,
                "analysis_range": None,
                "sources": [],
            },
            "candidates": candidates,
            "uploads": [],
        },
        "settings_version": "test-0",
        "work_dir": str(work_dir),
        "uploads": [],
        "data_mode": "live",
    }


class StubClient:
    """호출부 대역. 실제 NVIDIA 응답이 아니다."""

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls = 0

    def predict_complex(self, polymers, **kwargs):
        self.calls += 1
        if self._error:
            raise self._error
        return self._response


# ---------------------------------------------------------------- 기존 구조 경로
def test_matching_experimental_structure_skips_prediction(tmp_path):
    candidates = [
        candidate(
            "trastuzumab",
            "Trastuzumab Fab",
            entity_sequence(TRASTUZUMAB, "heavy"),
            entity_sequence(TRASTUZUMAB, "light"),
        ),
        candidate(
            "pertuzumab",
            "Pertuzumab Fab",
            entity_sequence(PERTUZUMAB, "heavy"),
            entity_sequence(PERTUZUMAB, "light"),
        ),
    ]
    client = StubClient(error=AssertionError("예측을 호출하면 안 된다"))
    output, flow = run_flow(make_request(candidates, tmp_path), client=client)

    validate(output, "LogicOutput")
    assert flow.run_status() == "completed"
    assert client.calls == 0

    for progress in flow.candidate_progress():
        steps = {s["step_id"]: s["status"] for s in progress["steps"]}
        assert progress["status"] == "completed"
        assert steps["prediction"] == "skipped"
        assert steps["structure_comparison"] == "completed"

    kinds = {s["kind"] for s in output["result"]["structures"]}
    assert kinds == {"experimental"}


def test_contact_evidence_matches_precomputed_file(tmp_path):
    candidates = [
        candidate(
            "trastuzumab",
            "Trastuzumab Fab",
            entity_sequence(TRASTUZUMAB, "heavy"),
            entity_sequence(TRASTUZUMAB, "light"),
        ),
        candidate(
            "pertuzumab",
            "Pertuzumab Fab",
            entity_sequence(PERTUZUMAB, "heavy"),
            entity_sequence(PERTUZUMAB, "light"),
        ),
    ]
    output, _ = run_flow(make_request(candidates, tmp_path), client=StubClient())
    contacts = json.loads(
        (structures.REPO_ROOT / "frontend/public/structures/contacts.json").read_text()
    )

    for cid, pdb_id in (("trastuzumab", TRASTUZUMAB), ("pertuzumab", PERTUZUMAB)):
        found = next(
            e
            for e in output["result"]["evidence"]
            if e["candidate_id"] == cid and e["topic"] == "interface_contact_residues"
        )
        assert found["measurement_state"] == "measured"
        assert found["value"] == len(contacts[pdb_id]["residues"])
        assert found["unit"] == "residue"
        assert len(found["residues"]) == len(contacts[pdb_id]["residues"])


def test_glycan_bearing_structure_gets_context_condition(tmp_path):
    """1N8Z·1S78 모두 당쇄 entity가 있으므로 주변 구조 조건이 따로 생긴다."""
    candidates = [
        candidate(
            "trastuzumab",
            "Trastuzumab Fab",
            entity_sequence(TRASTUZUMAB, "heavy"),
            entity_sequence(TRASTUZUMAB, "light"),
        ),
        candidate(
            "pertuzumab",
            "Pertuzumab Fab",
            entity_sequence(PERTUZUMAB, "heavy"),
            entity_sequence(PERTUZUMAB, "light"),
        ),
    ]
    output, _ = run_flow(make_request(candidates, tmp_path), client=StubClient())
    context = [c for c in output["result"]["conditions"] if c["kind"] == "context"]
    assert {c["candidate_id"] for c in context} == {"trastuzumab", "pertuzumab"}
    assert all("glycan" in c["included_components"] for c in context)
    assert all(c["gaps"] for c in context)


# ---------------------------------------------------------------- 자료 부족 보류
def test_short_sequences_hold_instead_of_predicting(tmp_path):
    """UI 모의 입력처럼 짧은 서열은 예측을 호출하지 않고 보류한다."""
    candidates = [
        candidate("mock-a", "모의 후보 1", "ACDE", "FGHI"),
        candidate("mock-b", "모의 후보 2", "ACDE", "FGHI"),
    ]
    client = StubClient(error=AssertionError("자료가 부족하면 호출하면 안 된다"))
    output, flow = run_flow(make_request(candidates, tmp_path), client=client)

    validate(output, "LogicOutput")
    assert client.calls == 0
    # 후보별로 보류 의견이 남으므로 실행 전체는 partial이다.
    # (Run 상태 enum에 held가 없다. 이 대응은 G1에서 확인이 필요하다.)
    assert flow.run_status() == "partial"
    for progress in flow.candidate_progress():
        steps = {s["step_id"]: s["status"] for s in progress["steps"]}
        assert steps["prediction"] == "held"
        assert progress["status"] == "partial"
    assert all(o["decision"] == "hold" for o in output["result"]["opinions"])
    assert not output["result"]["structures"]


# ---------------------------------------------------------------- 입력 오류
def test_invalid_characters_fail_before_lookup(tmp_path):
    candidates = [
        candidate("bad", "잘못된 입력", "ACDE123!!", "FGHI"),
        candidate("mock-b", "모의 후보 2", "ACDE", "FGHI"),
    ]
    output, flow = run_flow(make_request(candidates, tmp_path), client=StubClient())
    validate(output, "LogicOutput")

    progress = next(p for p in flow.candidate_progress() if p["candidate_id"] == "bad")
    steps = {s["step_id"]: s["status"] for s in progress["steps"]}
    assert progress["status"] == "failed"
    assert steps["input_mapping"] == "failed"
    assert steps["evidence_review"] == "skipped"


def test_analysis_range_beyond_sequence_fails(tmp_path):
    bad = candidate("bad", "구간 초과", "ACDEFGHIKL", "FGHI")
    bad["heavy_analysis_range"] = {"start": 1, "end": 999}
    candidates = [bad, candidate("mock-b", "모의 후보 2", "ACDE", "FGHI")]
    _, flow = run_flow(make_request(candidates, tmp_path), client=StubClient())
    progress = next(p for p in flow.candidate_progress() if p["candidate_id"] == "bad")
    assert progress["status"] == "failed"
    assert "999" in progress["reason"]


def test_missing_target_fails_every_candidate(tmp_path):
    request = make_request(
        [candidate("a", "후보", "ACDE", "FGHI"), candidate("b", "후보2", "ACDE", "FGHI")],
        tmp_path,
    )
    request["input"]["target"]["identifier"] = None
    request["input"]["target"]["fasta"] = None
    with pytest.raises(Exception):
        # 표적이 비면 ReviewInput 자체가 계약 위반이다.
        Flow(request)


# ---------------------------------------------------------------- 예측 경로
def _long(seq: str, n: int = 120) -> str:
    return (seq * ((n // len(seq)) + 1))[:n]


def _prediction_candidates() -> list[dict]:
    return [
        candidate("novel-a", "미공개 후보 A", _long("ACDEFGHIKLMNPQRSTVWY"), _long("WYVTSRQPNMLKIHGFEDCA")),
        candidate("novel-b", "미공개 후보 B", _long("KLMNPQRSTVWYACDEFGHI"), _long("EDCAWYVTSRQPNMLKIHGF")),
    ]


def test_prediction_path_records_returned_confidence(tmp_path):
    response = {
        "structures": [{"structure_id": "x", "structure": "data_predicted\n#\n"}],
        "confidence_scores": [0.77],
    }
    output, flow = run_flow(
        make_request(_prediction_candidates(), tmp_path, target_fasta=_long("HERTWOSEQ", 300)),
        client=StubClient(response=response),
    )
    validate(output, "LogicOutput")
    assert flow.run_status() == "completed"

    confidences = [e for e in output["result"]["evidence"] if e["topic"] == "prediction_confidence"]
    assert len(confidences) == 2
    assert all(e["measurement_state"] == "measured" and e["value"] == 0.77 for e in confidences)
    assert {s["kind"] for s in output["result"]["structures"]} == {"predicted"}
    # 예측 구조의 접촉 계산은 아직 없으므로 미실행으로 남아야 한다.
    contacts = [e for e in output["result"]["evidence"] if e["topic"] == "interface_contact_residues"]
    assert all(e["measurement_state"] == "not_run" and e["value"] is None for e in contacts)


def test_prediction_without_confidence_is_unknown_not_zero(tmp_path):
    response = {"structures": [{"structure": "data_x\n#\n"}]}
    output, _ = run_flow(
        make_request(_prediction_candidates(), tmp_path, target_fasta=_long("HERTWOSEQ", 300)),
        client=StubClient(response=response),
    )
    confidences = [e for e in output["result"]["evidence"] if e["topic"] == "prediction_confidence"]
    assert confidences and all(e["measurement_state"] == "unknown" for e in confidences)
    assert all(e["value"] is None for e in confidences)


def test_failed_call_is_not_reported_as_analysis(tmp_path):
    output, flow = run_flow(
        make_request(_prediction_candidates(), tmp_path, target_fasta=_long("HERTWOSEQ", 300)),
        client=StubClient(error=CallFailed("HTTP 500", status=500)),
    )
    validate(output, "LogicOutput")
    assert flow.run_status() == "failed"
    for progress in flow.candidate_progress():
        steps = {s["step_id"]: s["status"] for s in progress["steps"]}
        assert steps["prediction"] == "failed"
        assert steps["structure_comparison"] == "skipped"
    assert not output["result"]["structures"]
    assert all(o["decision"] == "not_assessed" for o in output["result"]["opinions"])


def test_empty_structures_response_is_failure(tmp_path):
    output, flow = run_flow(
        make_request(_prediction_candidates(), tmp_path, target_fasta=_long("HERTWOSEQ", 300)),
        client=StubClient(response={"structures": [], "confidence_scores": [0.9]}),
    )
    assert flow.run_status() == "failed"
    assert not output["result"]["structures"]


def test_missing_key_holds_rather_than_fails(tmp_path):
    output, flow = run_flow(
        make_request(_prediction_candidates(), tmp_path, target_fasta=_long("HERTWOSEQ", 300)),
        client=StubClient(error=MissingCredentials("NVIDIA_API_KEY가 없다")),
    )
    validate(output, "LogicOutput")
    for progress in flow.candidate_progress():
        steps = {s["step_id"]: s["status"] for s in progress["steps"]}
        assert steps["prediction"] == "held"
        assert progress["status"] == "partial"


# ---------------------------------------------------------------- 혼합 실행
def test_mixed_candidates_report_partial(tmp_path):
    candidates = [
        candidate(
            "trastuzumab",
            "Trastuzumab Fab",
            entity_sequence(TRASTUZUMAB, "heavy"),
            entity_sequence(TRASTUZUMAB, "light"),
        ),
        candidate("mock-b", "자료 부족 후보", "ACDE", "FGHI"),
    ]
    output, flow = run_flow(make_request(candidates, tmp_path), client=StubClient())
    validate(output, "LogicOutput")
    assert flow.run_status() == "partial"
    by_id = {p["candidate_id"]: p["status"] for p in flow.candidate_progress()}
    assert by_id == {"trastuzumab": "completed", "mock-b": "partial"}


def test_progress_updates_are_contract_valid(tmp_path):
    seen: list[dict] = []
    candidates = [
        candidate(
            "trastuzumab",
            "Trastuzumab Fab",
            entity_sequence(TRASTUZUMAB, "heavy"),
            entity_sequence(TRASTUZUMAB, "light"),
        ),
        candidate("mock-b", "자료 부족 후보", "ACDE", "FGHI"),
    ]
    run_flow(make_request(candidates, tmp_path), client=StubClient(), progress=seen.append)
    assert seen
    for update in seen:
        validate(update, "ProgressUpdate")
    assert {u["step_id"] for u in seen} == {
        "input_mapping",
        "evidence_review",
        "prediction",
        "structure_comparison",
        "reporting",
    }


# ---------------------------------------------------------------- 계약 규율
def test_unmeasured_evidence_never_carries_a_value(tmp_path):
    candidates = [
        candidate(
            "trastuzumab",
            "Trastuzumab Fab",
            entity_sequence(TRASTUZUMAB, "heavy"),
            entity_sequence(TRASTUZUMAB, "light"),
        ),
        candidate("mock-b", "자료 부족 후보", "ACDE", "FGHI"),
    ]
    output, _ = run_flow(make_request(candidates, tmp_path), client=StubClient())
    for e in output["result"]["evidence"]:
        if e["measurement_state"] != "measured":
            assert e["value"] is None
            assert e["reason"]
        else:
            assert e["unit"] and e["definition"]


def test_partial_sequence_match_does_not_count_as_same_candidate(tmp_path):
    """중쇄만 1N8Z와 같고 경쇄가 다르면 기존 구조로 확정하지 않는다."""
    candidates = [
        candidate(
            "half-match",
            "중쇄만 일치",
            entity_sequence(TRASTUZUMAB, "heavy"),
            _long("WYVTSRQPNMLKIHGFEDCA"),
        ),
        candidate("mock-b", "자료 부족 후보", "ACDE", "FGHI"),
    ]
    output, _ = run_flow(
        make_request(candidates, tmp_path, target_fasta=_long("HERTWOSEQ", 300)),
        client=StubClient(response={"structures": [{"structure": "data_x\n#\n"}]}),
    )
    made = [s for s in output["result"]["structures"] if s["candidate_id"] == "half-match"]
    assert made and made[0]["kind"] == "predicted"
