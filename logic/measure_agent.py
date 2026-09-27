"""NAT 에이전트 측정 (nat-agent-loop.md 7절). 실제 NVIDIA를 부른다.

    uv run python -m logic.measure_agent --repeat 3
"""

from __future__ import annotations

import argparse
import collections
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


def _take_http_attempts() -> list[dict]:
    """전송 계층의 시도 기록을 가져온다. NAT가 없는 환경에서는 빈 목록이다."""
    try:
        from . import nat_model
    except ImportError:
        return []
    return nat_model.take_attempts()


def _one(name: str, mode: str) -> dict:
    os.environ["LOGIC_AGENT_MODE"] = mode
    with tempfile.TemporaryDirectory() as tmp:
        cand = SCENARIOS[name]()
        # 컨트롤러가 후보 2건 이상을 요구한다. filler는 입력 오류로 즉시 걸러지므로
        # 측정 대상 시나리오 후보의 판단 순서에 영향을 주지 않는다.
        candidates = [cand, _filler()]
        t = time.time()
        _take_http_attempts()  # 이전 회차 기록을 이 행에 섞지 않는다
        output, flow = run_flow(make_request(candidates, Path(tmp), target_fasta=TARGET))
        elapsed = round(time.time() - t, 1)
    cid = cand["candidate_id"]
    trace = flow.agent_traces.get(cid, [])
    opinion = next((o for o in output["result"]["opinions"] if o["candidate_id"] == cid), {})
    notes = [c["note"] for c in trace if not c.get("accepted") and c.get("note")]
    reason = opinion.get("reason") or ""
    # 오류는 후보 단위로 본다. 같은 흐름의 대조용 후보가 받은 429를 이 행의
    # 실패로 세면 측정이 오염된다.
    error = flow.agent_errors.get(cid)
    attempts = _take_http_attempts()
    statuses = collections.Counter(str(a["status"]) for a in attempts)
    fatal_429 = any("429" in text or "Too Many Requests" in text for text in (reason, error or ""))
    return {
        # 기록 파일은 이어붙이므로, 어느 실행의 줄인지 나중에 구분할 수 있게 시각을 남긴다.
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "scenario": name, "mode": mode, "seconds": elapsed,
        # 규칙 마무리 사유를 그대로 남긴다. 이것이 없으면 API 한도(429)로 실패한
        # 실행과 모델 빈 응답으로 실패한 실행이 기록상 똑같이 보인다(둘 다
        # calls=0, rule_finish=True). 2026-09-26에 그 구분이 안 돼 무효 자료
        # 세 벌을 만들었다 — 원인 판정이 stderr 로그에만 있었다.
        "reason": reason,
        "agent_error": error,
        # 복구된 429는 agent_errors까지 올라오지 않는다. 전송 계층 기록으로
        # 복구된 한도·빈 200 응답·미처리 오류를 각각 센다.
        "rate_limited": fatal_429,
        "http_statuses": dict(statuses),
        "http_429_recovered": statuses.get("429", 0) > 0 and not fatal_429,
        "http_empty_responses": sum(1 for a in attempts if a["status"] == 200 and not a["emitted"]),
        "http_attempts": attempts,
        "code_calls": sum(c.get("executed_by") == "code" for c in trace),
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
    # 시나리오를 골라 돌린다. Boltz-2를 부르는 것은 variant 하나뿐이므로
    # (나머지는 공개 구조와 일치하거나 입력 단계에서 끝난다), 빈 응답률처럼
    # 모델 쪽만 보는 측정은 variant를 빼서 유료 예측 호출 없이 할 수 있다.
    ap.add_argument("--scenario", default="", help=f"쉼표로 구분. 기본은 전부: {','.join(SCENARIOS)}")
    ap.add_argument("--no-rule", action="store_true", help="규칙 모드 대조 실행을 건너뛴다(모델 호출 절약)")
    ap.add_argument("--out", default="measure-agent.jsonl", help="work/ 아래 기록 파일 이름")
    # 실측(2026-09-26): 연속으로 돌리면 1회 성공 뒤 곧바로 429가 이어졌다.
    # 실행 사이를 띄우면 한도에 걸리지 않고 표본을 모을 수 있다.
    ap.add_argument("--sleep", type=float, default=0.0, help="실행 사이 대기 초. 429를 피하려면 30 이상을 권한다")
    args = ap.parse_args()
    names = [n.strip() for n in args.scenario.split(",") if n.strip()] or list(SCENARIOS)
    unknown = [n for n in names if n not in SCENARIOS]
    if unknown:
        ap.error(f"모르는 시나리오: {', '.join(unknown)}. 가능한 값: {', '.join(SCENARIOS)}")
    out = Path(__file__).resolve().parent.parent / "work" / args.out
    out.parent.mkdir(exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        for name in names:
            plan = ([] if args.no_rule else [("rule", None)]) + [("nat", i) for i in range(args.repeat)]
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
                # 한도에 걸리면 남은 실행은 전부 같은 이유로 실패한다. 계속
                # 돌리면 무효 자료만 쌓이고, 그 줄들이 빈 응답처럼 보인다.
                # 여기서 멈추고 측정이 무효임을 분명히 알린다.
                if args.sleep and not r["rate_limited"]:
                    print(f"  … {args.sleep:g}초 대기(한도 회피)", flush=True)
                    time.sleep(args.sleep)
                if r["rate_limited"]:
                    print(f"\n✗ 측정 중단: API 한도(429)에 걸렸다. 이 실행의 기록은 무효다.\n"
                          f"  사유: {r['reason']}\n"
                          f"  한도가 풀린 뒤 다시 돌린다. 무효 줄은 {out.name}에서 지우거나 파일을 옮긴다.",
                          flush=True)
                    raise SystemExit(2)
    print("기록:", out, flush=True)


if __name__ == "__main__":
    main()
