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
from .tests.test_flow import PERTUZUMAB, TRASTUZUMAB, _long, candidate, entity_sequence, make_request
from .tests.test_flow_decisions import _filler

# 예측 경로에 쓰는 합성 표적 서열. 테스트와 같은 값이며 실제 HER2 서열이 아니다.
TARGET = _long("HERTWOSEQ", 300)

SCENARIOS = {
    "trastuzumab": lambda: candidate("cand-t", "trastuzumab",
                                     entity_sequence(TRASTUZUMAB, "heavy"), entity_sequence(TRASTUZUMAB, "light")),
    "pertuzumab": lambda: candidate("cand-p", "pertuzumab",
                                    entity_sequence(PERTUZUMAB, "heavy"), entity_sequence(PERTUZUMAB, "light")),
    "variant": lambda: candidate("cand-v", "variant", _long("QVQLVESGG"), _long("DIQMTQSPS")),
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
