"""실행부 진입점 (D4의 B쪽).

서비스 운영부가 LogicRequest JSON을 주면 분석을 실행하고 LogicOutput JSON을 돌려준다.
HTTP·DB를 알지 못하며, 작업 점유·재시작·상태 보존은 운영부의 몫이다.

    python -m logic.run --request req.json --out out.json [--progress progress.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .contract import ContractError
from .flow import run_flow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HER2 후보 검토 실행부")
    parser.add_argument("--request", required=True, type=Path, help="LogicRequest JSON 경로")
    parser.add_argument("--out", required=True, type=Path, help="LogicOutput을 쓸 경로")
    parser.add_argument("--progress", type=Path, help="ProgressUpdate를 이어 쓸 JSONL 경로")
    args = parser.parse_args(argv)

    request = json.loads(args.request.read_text(encoding="utf-8"))

    progress_file = None
    if args.progress:
        args.progress.parent.mkdir(parents=True, exist_ok=True)
        progress_file = args.progress.open("a", encoding="utf-8")

    def on_progress(update: dict) -> None:
        line = json.dumps(update, ensure_ascii=False)
        if progress_file:
            progress_file.write(line + "\n")
            progress_file.flush()
        print(line, file=sys.stderr)

    try:
        output, flow = run_flow(request, progress=on_progress)
    except ContractError as exc:
        print(f"계약 위반으로 실행하지 않았다:\n{exc}", file=sys.stderr)
        return 2
    finally:
        if progress_file:
            progress_file.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    status = flow.run_status()
    print(f"실행 상태={status}", file=sys.stderr)
    for progress in flow.candidate_progress():
        print(f"  {progress['candidate_id']}: {progress['status']}", file=sys.stderr)
    # 실행 자체는 끝났으므로 0. 후보별 보류·실패는 결과 안에서 구분한다.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
