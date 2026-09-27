"""고정 평가 사례를 지정한 샘플 수로 한 번 부른다. 유료 호출이다.

    python docs/topics/her2/assets/goldset/fetch_benchmark_samples.py \
        --case 8JYR --samples 5 --env /path/to/.env

응답 파일이 이미 있으면 부르지 않는다. 429는 재시도하지 않고 기록한 뒤 멈춘다.
서열은 고정 평가 매니페스트에서 읽는다. 8JYR·3N85의 표적 construct는
1N8Z·1S78과 달라서 catalog(verify_prediction.py)가 다루지 못한다.
"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(ROOT))

from logic import structures  # noqa: E402
from logic.env import load_env  # noqa: E402
from logic.nvidia_client import NvidiaClient  # noqa: E402

MANIFEST = HERE / "generated/agent-benchmark-manifest.json"


class OneAttemptClient(NvidiaClient):
    def _post(self, *args, **kwargs):
        # 평가 중 429는 재시도하지 않는다. 유료 호출을 두 번 내지 않으려는 것이다.
        return super()._post(*args, **{**kwargs, "waits": ()})


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--samples", type=int, required=True)
    ap.add_argument("--env", type=Path)
    args = ap.parse_args()

    cases = json.loads(MANIFEST.read_text())["cases"]
    case = next((c for c in cases if c["id"] == args.case), None)
    if case is None:
        ap.error(f"{args.case}는 고정 평가 매니페스트에 없다. 있는 것: "
                 + ", ".join(c["id"] for c in cases))
    sequences = {r: structures.normalize_sequence(s) for r, s in case["sequences"].items()}
    polymers = [{"id": cid, "molecule_type": "protein", "sequence": sequences[role]}
                for cid, role in [("A", "target"), ("H", "heavy"), ("L", "light")]]

    work = ROOT / "work/quality" / f"{args.case}-{args.samples}"
    work.mkdir(parents=True, exist_ok=True)
    path = work / "boltz2_response.json"
    if path.exists():
        print(f"이미 있다: {path} (호출하지 않음)")
        return
    load_env(args.env)
    print(f"{args.case} 표적 {len(sequences['target'])}aa, 중쇄 {len(sequences['heavy'])}aa, "
          f"경쇄 {len(sequences['light'])}aa → diffusion_samples={args.samples} 호출")
    response = OneAttemptClient(work).predict_complex(polymers, diffusion_samples=args.samples)
    path.write_text(json.dumps(response), encoding="utf-8")
    print(f"저장: {path}")
    print(f"구조 {len(response.get('structures') or [])}개, "
          f"confidence={response.get('confidence_scores')}")


if __name__ == "__main__":
    main()
