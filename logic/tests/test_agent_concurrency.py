"""병렬 도구 호출 경합 (최종 전체 브랜치 리뷰 I1).

NAT/langgraph의 ToolNode는 모델 응답 하나에 담긴 도구 호출을 전부
`asyncio.gather`로 동시에 실행하고, 각 래퍼는 `asyncio.to_thread`로 그
도구를 실제로 부른다. 한 후보에 대해 같은 모델 메시지가
predict_structure를 두 번 발행하면, 락이 없을 때는 두 스레드가 거의
동시에 `_gate`를 통과해 Boltz-2가 두 번 불릴 수 있다(실측: 구조·조건·
판정 기록이 중복으로 남았다).

여기서는 그 경합을 실제로 재현한다 — 느리게 답하며 호출 횟수를 세는
클라이언트로 predict_structure 두 개를 `asyncio.gather` +
`asyncio.to_thread`로 동시에 돌려서, 정확히 한 번만 예측되고 한 번은
거부되는지 본다. NVIDIA를 실제로 부르지 않는다.
"""

from __future__ import annotations

import asyncio
import threading
import time

from logic.agent_session import CandidateSession, CandidateTools
from logic.flow import Flow
from logic.tests.test_flow import _long, candidate, make_request


TARGET = _long("HERTWASEQ", 300)


def _filler():
    return candidate("filler", "입력 오류 후보", ">bad\n123", ">bad\n456")


def _variant():
    return candidate("cand-v", "variant", _long("QVQLVESGG"), _long("DIQMTQSPS"))


class SlowCountingClient:
    """predict_complex를 부를 때마다 잠깐 잠들었다가 세어 둔다.

    잠을 자는 동안 두 번째 호출이 같은 관문을 통과할 여유를 준다 —
    락이 없으면 여기서 경합이 드러난다.
    """

    def __init__(self):
        self.predictions = 0
        self._lock = threading.Lock()

    def predict_complex(self, polymers, **kwargs):
        time.sleep(0.05)
        with self._lock:
            self.predictions += 1
        return {
            "structures": [{"structure": "data_x\n#\n"}],
            "confidence_scores": [0.87],
        }

    def chat(self, model, messages, **kwargs):  # pragma: no cover - 이 시험에서는 안 쓴다
        raise AssertionError("이 시험은 모델을 부르지 않는다")


def _setup(tmp_path):
    client = SlowCountingClient()
    cand = _variant()
    flow = Flow(make_request([cand, _filler()], tmp_path, target_fasta=TARGET), client=client)
    session = CandidateSession(cand)
    tools = CandidateTools(flow, session)
    return client, flow, session, tools


def test_two_concurrent_predict_calls_only_predict_once(tmp_path):
    client, flow, session, tools = _setup(tmp_path)
    tools.check_input()
    tools.lookup_public_structure()

    async def _run():
        return await asyncio.gather(
            asyncio.to_thread(tools.predict_structure, "일치하는 공개 구조가 없어 새로 만든다."),
            asyncio.to_thread(tools.predict_structure, "동시에 같은 이유로 예측한다."),
        )

    out1, out2 = asyncio.run(_run())

    assert client.predictions == 1, "락이 없으면 두 스레드가 모두 Boltz-2를 부른다"

    outcomes = sorted([out1, out2], key=lambda s: s.startswith("거부:"))
    accepted, refused = outcomes[0], outcomes[1]
    assert not accepted.startswith("거부:")
    assert refused.startswith("거부:")
    assert session.structure_id is not None

    accepted_calls = [c for c in session.calls if c["tool"] == "predict_structure" and c["accepted"]]
    refused_calls = [c for c in session.calls if c["tool"] == "predict_structure" and not c["accepted"]]
    assert len(accepted_calls) == 1
    assert len(refused_calls) == 1
