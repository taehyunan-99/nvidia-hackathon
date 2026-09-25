"""자격 증명 확인 (계획서 B-01의 첫 단계).

    python -m logic.check_key

`.env`의 키를 읽어 실제로 모델 목록을 조회한다. 키 값은 출력하지 않는다.
이 명령이 성공해야 예측 경로를 실제 호출로 검증했다고 말할 수 있다.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from . import env
from .nvidia_client import CallFailed, MissingCredentials, NvidiaClient


def main() -> int:
    print(f"키 상태: {env.describe_key()}")
    key, _ = env.find_key()
    if not key:
        print(
            "\n.env가 없거나 비어 있다. 다음 순서로 넣는다:\n"
            "  1. cp .env.example .env\n"
            "  2. https://build.nvidia.com/settings/api-keys 에서 로그인 후 키 발급\n"
            "  3. .env의 NVIDIA_API_KEY= 뒤에 붙여넣기\n"
            "  4. python -m logic.check_key 다시 실행\n"
            "키 값은 채팅·이슈·커밋에 넣지 않는다.",
            file=sys.stderr,
        )
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        client = NvidiaClient(Path(tmp))
        try:
            models = client.list_models()
        except MissingCredentials as exc:
            print(f"\n확인 실패: {exc}", file=sys.stderr)
            return 1
        except CallFailed as exc:
            print(f"\n호출 실패: {exc}", file=sys.stderr)
            print("키가 만료됐거나 권한이 없을 수 있다. 발급 페이지에서 다시 확인한다.", file=sys.stderr)
            return 1

    nemotron = sorted(m for m in models if "nemotron" in m.lower())
    print(f"\n호출 성공. 모델 {len(models)}개, nemotron 계열 {len(nemotron)}개.")
    for model in nemotron[:10]:
        print(f"  - {model}")
    if len(nemotron) > 10:
        print(f"  … 외 {len(nemotron) - 10}개")
    print("\n이제 예측 경로를 실제 호출로 검증할 수 있다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
