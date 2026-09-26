"""NAT 에이전트 측정 (nat-agent-loop.md 7절). 실제 NVIDIA를 부른다.

    uv run python -m logic.measure_agent --repeat 3
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import tempfile
import time
from pathlib import Path

from .env import load_env
from .flow import run_flow
from .tests.test_flow import PERTUZUMAB, TRASTUZUMAB, candidate, entity_sequence, make_request
from .tests.test_flow_decisions import _filler

# 예측 경로에 쓰는 표적 서열. 실제 HER2 표적(1N8Z의 target 사슬)이다.
#
# Task 6b 진단(2026-09-26, work/task-6b-diag/call_log.jsonl): 이전에는 합성
# 서열 `_long("HERTWOSEQ", 300)`을 썼는데, 그 반복 안에 든 문자 "O"가
# Boltz-2 API에서 HTTP 422 "Invalid protein sequence. Contains invalid
# characters: O"로 거부됐다. `_check_input`의 허용 문자 집합(ACDEFGHIKLMNPQRSTVWYXBZUO)은
# 이 O를 통과시키므로 로컬 입력 검사로는 걸러지지 않았다 — variant 시나리오가
# 규칙·에이전트 3회 모두 failed/not_assessed로 끝난 원인이다. service.demo_input의
# prediction_demo()가 쓰는 실제 서열로 바꿔 이 문제를 없앤다.
TARGET = entity_sequence(TRASTUZUMAB, "target")


def _variant_heavy() -> str:
    """Pertuzumab 중쇄에서 한 자리만 바꾼 가상 변이체. service.demo_input.prediction_demo()와 같은 방식."""
    heavy = entity_sequence(PERTUZUMAB, "heavy")
    position = 30
    return heavy[:position] + ("A" if heavy[position] != "A" else "G") + heavy[position + 1 :]


SCENARIOS = {
    "trastuzumab": lambda: candidate("cand-t", "trastuzumab",
                                     entity_sequence(TRASTUZUMAB, "heavy"), entity_sequence(TRASTUZUMAB, "light")),
    "pertuzumab": lambda: candidate("cand-p", "pertuzumab",
                                    entity_sequence(PERTUZUMAB, "heavy"), entity_sequence(PERTUZUMAB, "light")),
    "variant": lambda: candidate("cand-v", "variant", _variant_heavy(), entity_sequence(PERTUZUMAB, "light")),
    "invalid": lambda: candidate("cand-x", "invalid", "QVQL123", "DIQM!!"),
    "short": lambda: candidate("cand-s", "short", "QVQLVESGG", "DIQMTQSPS"),
}


def _one(name: str, mode: str) -> dict:
    os.environ["LOGIC_AGENT_MODE"] = mode
    with tempfile.TemporaryDirectory() as tmp:
        cand = SCENARIOS[name]()
        # 컨트롤러가 후보 2건 이상을 요구한다. filler는 입력 오류로 즉시 걸러지므로
        # 측정 대상 시나리오 후보의 판단 순서에 영향을 주지 않는다.
        candidates = [cand, _filler()]
        t = time.time()
        output, flow = run_flow(make_request(candidates, Path(tmp), target_fasta=TARGET))
        elapsed = round(time.time() - t, 1)
    cid = cand["candidate_id"]
    trace = flow.agent_traces.get(cid, [])
    opinion = next((o for o in output["result"]["opinions"] if o["candidate_id"] == cid), {})
    notes = [c["note"] for c in trace if not c.get("accepted") and c.get("note")]
    return {
        "scenario": name, "mode": mode, "seconds": elapsed,
        "calls": len(trace), "refused": sum(1 for c in trace if not c["accepted"]),
        "rule_finish": "판단: 규칙" in (opinion.get("reason") or ""),
        "hit_limit": "반복 상한" in (opinion.get("reason") or ""),
        "status": flow.states[cid].status, "decision": opinion.get("decision"),
        "trace": [c["tool"] + ("" if c["accepted"] else "✗") for c in trace],
        "notes": notes,
    }


def main() -> None:
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args()
    out = Path(__file__).resolve().parent.parent / "work" / "measure-agent.jsonl"
    out.parent.mkdir(exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        for name in SCENARIOS:
            plan = [("rule", None)] + [("nat", i) for i in range(args.repeat)]
            for mode, _ in plan:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                print(f"▶ {ts} {name} {mode}", flush=True)
                r = _one(name, mode)
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
                line = (f"{r['scenario']:12} {r['mode']:4} {r['seconds']:6}s calls={r['calls']} "
                        f"refused={r['refused']} rule_finish={r['rule_finish']} limit={r['hit_limit']} "
                        f"{r['status']}/{r['decision']} {' → '.join(r['trace'])}")
                if r["notes"]:
                    line += " | " + " / ".join(r["notes"])
                print(line, flush=True)
    print("기록:", out, flush=True)


if __name__ == "__main__":
    main()
