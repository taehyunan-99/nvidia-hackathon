"""보류 대 예측 갈림길을 실제 에이전트로 채점한다.

관문은 공개 구조와 완전히 일치하지 않으면 predict_structure와 hold_candidate를
함께 연다(`logic/agent_session.py` allowed_tools). hold_candidate의 도구 설명은
"예측 입력으로 쓸 서열 자체가 없거나 너무 짧을 때만"이므로, 서열이 멀쩡한 실제
항체 10건의 정답은 전부 predict_structure다. 정답이 코드가 아니라 도구 설명에
적혀 있어 채점할 수 있다.

Boltz-2는 스텁으로 막는다 — 유료 예측 호출 0회. Nemotron만 부른다.

한도(429) 주의: 실측(2026-09-26)에서 에이전트는 모델 호출 3~4번 만에 429를 맞았다.
갈림길 선택은 3번째 호출에서 끝나므로 그 뒤 429가 나도 **이 채점에는 영향이 없다**.
따라서 `chose`가 잡히면 유효한 표본으로 센다. 다음 후보를 위해 충분히 쉰다.

    python docs/topics/her2/assets/goldset/score_hold_vs_predict.py --sleep 300
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GENERATED = HERE / "generated"


def _repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").exists() and (p / "logic").is_dir():
            return p
    raise SystemExit("저장소 뿌리를 찾지 못했다(pyproject.toml + logic/).")


ROOT = _repo_root(HERE)
sys.path.insert(0, str(ROOT))

from logic.env import load_env  # noqa: E402
from logic.flow import run_flow  # noqa: E402
from logic.tests.test_flow import TRASTUZUMAB, candidate, entity_sequence, make_request  # noqa: E402
from logic.tests.test_flow_decisions import _filler  # noqa: E402

# entity_id 역할(중쇄, 경쇄). RCSB 설명 문자열을 읽고 손으로 확인했다.
ROLE = {
    "3BE1": (2, 3), "3WSQ": (3, 2), "5O4G": (3, 2), "6ATT": (2, 3), "6BGT": (3, 2),
    "9L1S": (3, 2), "9T3R": (2, 1), "9T3S": (1, 2), "4P59": (2, 3), "8YRY": (2, 3),
}
TARGET_KIND = {"4P59": "HER3", "8YRY": "HER3"}
FORK_TOOLS = ("predict_structure", "hold_candidate", "use_experimental_structure")
GOLD_TOOL = "predict_structure"
TARGET = entity_sequence(TRASTUZUMAB, "target")


class StubBoltz:
    """Boltz-2 자리를 막는다. 유료 예측을 부르지 않는다."""

    def __init__(self):
        self.predictions = 0

    def predict_complex(self, polymers, **kw):
        self.predictions += 1
        return {"structures": [{"structure": "data_stub\n#\n"}], "confidence_scores": [0.5]}

    def chat(self, model, messages, **kw):
        from logic.nvidia_client import MissingCredentials
        raise MissingCredentials("채점 중에는 규칙 경로의 판단 호출을 막는다.")


def load_cases():
    data = json.loads((GENERATED / "pdb-sequences.json").read_text(encoding="utf-8"))
    out = []
    for pid, (h_id, l_id) in ROLE.items():
        ents = {int(e["entity_id"]): e for e in data[pid]["entities"]}
        out.append((pid, ents[h_id]["sequence"], ents[l_id]["sequence"]))
    return out


def run_one(pid: str, heavy: str, light: str) -> dict:
    cand = candidate(f"cand-{pid.lower()}", pid, f">h\n{heavy}", f">l\n{light}")
    started = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        req = make_request([cand, _filler()], Path(tmp), target_fasta=TARGET)
        client = StubBoltz()
        output, flow = run_flow(req, client=client)
        cid = cand["candidate_id"]
        trace = flow.agent_traces.get(cid, [])
        accepted = [c["tool"] for c in trace if c.get("accepted")]
        refused = [c for c in trace if c.get("accepted") is False]
        chose = next((n for n in accepted if n in FORK_TOOLS), None)
        op = next((o for o in output["result"]["opinions"] if o["candidate_id"] == cid), None)
        reason = (op or {}).get("reason", "")
        return {
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
            "pdb": pid,
            "target_kind": TARGET_KIND.get(pid, "HER2"),
            "seconds": round(time.time() - started, 1),
            "chose": chose,
            "gold": GOLD_TOOL,
            # 갈림길에 닿았는가. 닿았으면 그 뒤 429가 나도 이 채점에는 유효하다.
            "reached_fork": chose is not None,
            "correct": chose == GOLD_TOOL,
            "calls": len(trace),
            "refused": len(refused),
            "notes": [c.get("note", "")[:120] for c in refused],
            "boltz_calls": client.predictions,
            "rule_finish": "판단: 규칙" in reason,
            "rate_limited": "429" in reason or "Too Many Requests" in reason,
            "decision": (op or {}).get("decision"),
            "trace": [c["tool"] + ("" if c.get("accepted") else "✗") for c in trace],
        }


def summarise(path: Path) -> None:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    valid = [r for r in rows if r.get("reached_fork")]
    ok = sum(1 for r in valid if r["correct"])
    print()
    print(f"채점: {ok}/{len(valid)} 정답 — 갈림길에 닿은 표본만 셌다 (전체 기록 {len(rows)}건)")
    print(f"정답은 모두 {GOLD_TOOL} (서열이 충분히 길고 공개 구조 완전 일치가 없다)")
    for r in valid:
        if not r["correct"]:
            print(f"  오답 {r['pdb']} → {r['chose']}  {r['trace']}")
    missed = [r["pdb"] for r in rows if not r.get("reached_fork")]
    if missed:
        print("갈림길에 못 닿음(한도 등):", ", ".join(missed))
    print("유료 예측 호출:", sum(r["boltz_calls"] for r in rows), "(스텁이라 실제 비용 0)")


def main() -> None:
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=300.0,
                    help="후보 사이 대기 초. 한도 회복에 필요하다(실측 기준 300 권장)")
    ap.add_argument("--out", default="hold-vs-predict.jsonl", help="generated/ 아래 기록 파일")
    ap.add_argument("--only", default="", help="쉼표로 구분한 PDB ID만 돌린다")
    ap.add_argument("--summary", action="store_true", help="돌리지 않고 기존 기록만 집계한다")
    args = ap.parse_args()

    path = GENERATED / args.out
    if args.summary:
        summarise(path)
        return

    os.environ["LOGIC_AGENT_MODE"] = "nat"
    done = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("reached_fork"):
                    done.add(r["pdb"])
    want = {s.strip().upper() for s in args.only.split(",") if s.strip()}
    cases = [c for c in load_cases() if c[0] not in done and (not want or c[0] in want)]
    print(f"남은 후보 {len(cases)}건 (갈림길까지 간 {len(done)}건은 건너뛴다)", flush=True)

    for i, (pid, heavy, light) in enumerate(cases):
        if i:
            print(f"   {args.sleep:.0f}초 쉰다(한도 회복)", flush=True)
            time.sleep(args.sleep)
        print(f"▶ {datetime.datetime.now():%H:%M:%S} {pid}", flush=True)
        row = run_one(pid, heavy, light)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if not row["reached_fork"]:
            mark = "갈림길 못 닿음"
        else:
            mark = "정답" if row["correct"] else "오답"
        print(f"   {mark} chose={row['chose']} calls={row['calls']} refused={row['refused']} "
              f"429={row['rate_limited']} {row['seconds']}s", flush=True)

    summarise(path)


if __name__ == "__main__":
    main()
