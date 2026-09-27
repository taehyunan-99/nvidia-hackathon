"""실제 응답을 제품 선택 코드에 넣어 채점한다. --fetch만 유료 호출(캐시 없을 때 1회).

python docs/topics/her2/assets/goldset/verify_prediction.py --case 1S78 --samples 5 --fetch --env /path/to/.env
python docs/topics/her2/assets/goldset/verify_prediction.py --case 1N8Z --samples 5 --response /path/to/boltz2_response.json
"""
import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(ROOT))

from logic import structures
from logic.env import load_env
from logic.flow import Flow, select_structure
from logic.nvidia_client import NvidiaClient
from logic.tests.test_flow import candidate, entity_sequence, make_request, StubClient
from logic.tests.test_flow_decisions import _filler
from sweep_boltz import score_prediction


class OneAttemptClient(NvidiaClient):
    def _post(self, *args, **kwargs):
        # ponytail: 평가 중 429는 재시도하지 않고 기록한 뒤 멈춘다.
        return super()._post(*args, **{**kwargs, "waits": ()})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", choices=["1N8Z", "1S78"], required=True)
    ap.add_argument("--samples", type=int, choices=[1, 5], required=True)
    ap.add_argument("--response", type=Path)
    ap.add_argument("--env", type=Path)
    ap.add_argument("--fetch", action="store_true")
    args = ap.parse_args()
    work = ROOT / "work" / "quality" / f"{args.case}-{args.samples}"
    work.mkdir(parents=True, exist_ok=True)
    path = args.response or work / "boltz2_response.json"
    sequences = {r: structures.normalize_sequence(entity_sequence(args.case, r))
                 for r in ("target", "heavy", "light")}
    polymers = [{"id": c, "molecule_type": "protein", "sequence": sequences[r]}
                for c, r in [("A", "target"), ("H", "heavy"), ("L", "light")]]
    if not path.exists():
        if not args.fetch or args.response:
            ap.error("응답 파일이 없다. 신규 호출은 --fetch로 명시한다.")
        load_env(args.env)
        response = OneAttemptClient(work).predict_complex(polymers, diffusion_samples=args.samples)
        path.write_text(json.dumps(response), encoding="utf-8")
    response = json.loads(path.read_text())
    references = json.loads((HERE / "generated/reference-contacts.json").read_text())
    ref = next(r for r in references if r["pdb"] == args.case)
    positions = set(ref["copies"][0]["target_side_resnum"])
    scores = [score_prediction(s["structure"], positions, sequences["target"], sequences["target"])
              for s in response["structures"]]
    if not scores or any("error" in s for s in scores):
        raise ValueError("채점할 실제 mmCIF가 없다. 축약 로그는 원본 응답으로 사용할 수 없다.")
    cand = candidate("measured", args.case, sequences["heavy"], sequences["light"])
    flow = Flow(make_request([cand, _filler()], work, target_fasta=sequences["target"]),
                client=StubClient())
    sid = flow._record_predicted("measured", response, sequences)
    index, confidences = select_structure(response)
    assert sid is not None and index is not None
    # 선택 지점은 제품 코드가 돌려준 인덱스를 쓴다. 같은 본문이 두 번 오면
    # 파일 대조로는 어느 것을 골랐는지 되찾을 수 없다.
    assert (work / f"{sid}.cif").read_text() == response["structures"][index]["structure"]
    evidence = next(e for e in flow.evidence if e["topic"] == "prediction_confidence")
    assert evidence["value"] == confidences[index]
    reference_path = ROOT / "frontend/public/structures" / f"{args.case}.cif"
    log = work / "call_log.jsonl"
    records = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    recorded = [r for r in records if r.get("ok") and r.get("kind") == "boltz2.predict"]
    row = {
        "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "case": args.case, "diffusion_samples": args.samples,
        "http_seconds": round(recorded[-1]["elapsed_s"], 3) if recorded else None,
        "response_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "response_path": str(path.resolve()),
        "reference_url": f"https://files.rcsb.org/download/{args.case}.cif",
        "reference_sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest(),
        "sequence_sha256": {r: hashlib.sha256(s.encode()).hexdigest() for r, s in sequences.items()},
        "returned_structures": len(scores), "selected_index": index,
        "selected_confidence": evidence["value"], "selected_score": scores[index],
        "per_structure": scores,
        "limitation": "Retrospective known structures; no independent seed/model-version control or affinity validation.",
    }
    output = HERE / "generated" / f"verified-{args.case}-{args.samples}.json"
    output.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(row, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
