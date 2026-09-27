"""캐시된 실제 예측으로 기준 계면 겹침 근거를 검산한다. API를 부르지 않는다.

    python docs/topics/her2/assets/goldset/check_epitope_overlap.py
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(ROOT))

from logic import analysis, structures  # noqa: E402
from logic.tests.test_flow import entity_sequence  # noqa: E402

SOURCE = {"title": "캐시된 Boltz-2 응답", "url": "https://build.nvidia.com/mit/boltz2",
          "record_id": "epitope-overlap-check"}


def mapping_for(cif_text: str, target_sequence: str) -> list[dict]:
    """서열로 표적·항체 사슬을 찾는다(flow._predicted_chain_mapping과 같은 방식)."""
    entities, _ = structures.parse_entities(cif_text)
    by_seq = {structures.normalize_sequence(e.sequence): e.strand_ids[0]
              for e in entities if e.sequence and e.strand_ids}
    target = by_seq.get(structures.normalize_sequence(target_sequence))
    others = sorted(c for c in by_seq.values() if c != target)
    if target is None or len(others) != 2:
        raise SystemExit(f"사슬을 찾지 못했다 target={target} others={others}")
    return [{"role": "target", "label_asym_id": target},
            {"role": "heavy", "label_asym_id": others[0]},
            {"role": "light", "label_asym_id": others[1]}]


def benchmark_case(pid: str) -> tuple[Path, str, bool]:
    """고정 8사례의 예측 구조. 후보 항체는 트라스투주맙이 아니다."""
    run = ROOT / "work/agent-benchmark/runs" / f"{pid}-nat"
    result = json.loads((run / "output.json").read_text())["result"]
    predicted = next(s for s in result["structures"]
                     if s["candidate_id"] == "subject" and s["kind"] == "predicted")
    artifact = next(a for a in result["artifacts"] if a["artifact_id"] == predicted["artifact_id"])
    manifest = json.loads((HERE / "generated/agent-benchmark-manifest.json").read_text())
    seq = next(c for c in manifest["cases"] if c["id"] == pid)["sequences"]["target"]
    return run / artifact["file_name"], seq, False


def quality_case(pid: str) -> tuple[Path, str, bool]:
    """verify_prediction.py가 남긴 예측 구조. 1N8Z 후보는 트라스투주맙 자신이다."""
    work = ROOT / "work/quality" / f"{pid}-1"
    cif = next(p for p in work.glob("st-*.cif"))
    return cif, entity_sequence(pid, "target"), pid == "1N8Z"


def main() -> None:
    rows = []
    for pid, loader in (("1N8Z", quality_case), ("1S78", quality_case),
                        ("8JYR", benchmark_case), ("3N85", benchmark_case)):
        path, target_seq, is_reference_antibody = loader(pid)
        text = path.read_text()
        m = analysis.reference_epitope_overlap_measurement(
            path, mapping_for(text, target_seq), target_seq, SOURCE)
        rows.append({"case": pid, "candidate_is_trastuzumab": is_reference_antibody,
                     "prediction_sha256": hashlib.sha256(text.encode()).hexdigest(),
                     "measurement_state": m.state, "overlap_fraction": m.value,
                     "overlapping_target_residues": [r["label_seq_id"] for r in (m.residues or [])],
                     "reason": m.reason})
    out = {"reference_complex": analysis.REFERENCE_COMPLEX,
           "note": ("캐시된 응답만 쓴다. 새 API 호출 0회. 겹침 비율은 예측 접촉이 틀렸다는 판정이 "
                    "아니라, 후보가 트라스투주맙과 다른데 비율이 높으면 학습에서 본 계면을 "
                    "재현한 예측일 수 있다는 신호다."),
           "cases": rows}
    (HERE / "generated/epitope-overlap-check.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
