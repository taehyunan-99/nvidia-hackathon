# NAT 에이전트 루프 설계 — 로직 B

작성일 2026-09-26. 상태: **구현·측정 완료. 기본 모드 `nat`로 전환.** 담당 로직 B.
재측정 결과(§7 재측정)는 기준 1·2·3 모두 비해당으로 A(기본 에이전트) 유지, B(상태별 도구 노출)로 넘어가지 않았다. `max_empty_response_retries`(NAT 기본값 0)를 2로 올려 빈 응답 예외로 인한 규칙 마무리를 줄였다(재측정 15회 중 4회가 이 원인). 이 변경은 아직 재측정하지 않았다.
판단 흐름의 원 설계는 [agent-design.md](agent-design.md), 현재 실행부 상태는 [logic-b-handoff.md](logic-b-handoff.md)를 따른다.

## 1. 왜 바꾸는가

설계 문서는 "Nemotron이 상태에 따른 작업 선택, NAT가 함수 연결·실행 흐름·추적"이다. 현재 구현은 다르다.

- 흐름은 `logic/flow.py`의 고정 순서와 `if`다. 모델은 분기 2곳(`structure_source`, `review_opinion`)에서 선택지 하나를 고를 뿐이다.
- NAT는 코드와 의존성 어디에도 없다 (`logic/*.py`, `pyproject.toml` 검색 기준).

목표: **Nemotron이 NAT의 tool-calling 루프 안에서 다음에 실행할 도구를 직접 고른다.** 숫자 계산·입력 검사·호출 한도는 계속 코드가 쥔다.

## 2. 확인한 전제 (2026-09-26 실측)

| 항목 | 결과 | 근거 |
|---|---|---|
| Nemotron tool-calling | `nvidia/nemotron-3-super-120b-a12b`가 도구 2개 중 올바른 것을 1.6초에 호출, `finish_reason=tool_calls` | 기존 `NvidiaClient.chat(tools=...)`로 1회 호출 |
| NAT 설치 | `nvidia-nat[langchain]` 1.9.0, Python 3.13에서 설치됨. 약 676 MB | 임시 venv |
| NAT Python 범위 | `>=3.11,<3.14` | PyPI 메타데이터 |
| 기본 에이전트 | `tool_calling_agent`는 시작 시 도구 목록을 한 번 `bind_tools`하고 끝까지 쓴다. `max_iterations` 기본 15 | `nat/plugins/langchain/agent/tool_calling_agent/` |
| LLM 호출 방식 | NAT 에이전트는 응답을 **스트리밍**(`astream`)으로 받는다 | 같은 파일 `_invoke_llm` |
| NAT 루프 실호출 (0단계) | `tool_calling_agent` + 커스텀 도구 3개 + `nemotron-3-super` 스트리밍: 6.2초, 호출 순서 check→predict→finish, `return_direct`로 종료, `contextvars` 상태가 도구 안에서 보임. 최종 문장이 영어로 나옴 → 시스템 프롬프트에 한국어 지시 필요 | 임시 스크립트, 2026-09-26 |

확인됨(위 행): NVIDIA 엔드포인트에서 **스트리밍 + tool-calling 조합**이 이 모델로 동작함.

## 3. 결정: A로 시작하고 B로 넘어갈 수 있게 짠다

| | A — 기본 에이전트 + 도구 쪽 관문 | B — 상태별 도구 노출 |
|---|---|---|
| 루프 | NAT `tool_calling_agent` 그대로 | NAT `ToolCallAgentGraph`를 상속해 매 바퀴 허용 도구만 `bind_tools` |
| 모델이 보는 도구 | 전부 | 현재 상태에서 허용된 것만 |
| 순서 위반 | 도구가 거부 문구를 반환. 한 바퀴를 소모 | 발생하지 않음 |
| 직접 짜는 것 | 도구·관문·설정·연결부 | A 전부 + 그래프 하위 클래스와 커스텀 워크플로 등록 |

**전환 비용을 줄이는 원칙:** 관문 판단(`allowed_tools(session)`)을 도구 밖의 순수 함수 하나로 둔다. A에서는 각 도구가 이 함수로 거부 여부를 정하고, B에서는 같은 함수로 노출할 도구를 고른다. 도구·세션·폴백·결과 조립은 B에서 그대로 재사용한다. B의 그래프 하위 클래스가 `_invoke_llm` 재정의만으로 되는지는 미확인이다.

## 4. 구조

```
service/app.py ── run_flow(request)            # 시그니처·결과 계약(D5) 유지
                    └ Flow.run()
                        └ 후보마다 mode에 따라
                           ├ "nat":  NatRunner.run_candidate(session)
                           │           └ NAT tool_calling_agent (YAML)
                           │               └ 도구 7개 ── CandidateSession ── Flow 단계 메서드
                           │           └ 종료 상태가 아니면 → 규칙으로 이어서 마무리
                           └ "rule": 기존 _run_candidate (현행 그대로)
```

- **`CandidateSession`**: 후보 하나의 진행 상태(`input_checked`, `match`, `structure_id`, `compared`, `terminal`)와 거부·도구 호출 기록. Flow를 참조해 기존 `_emit`·기록 메서드를 쓴다. 진행 이벤트(ProgressUpdate)는 지금과 같게 나간다.
- **세션 전달**: NAT 도구는 설정으로 생성되므로 인자로 세션을 넘길 수 없다. 실행 직전 `contextvars`에 현재 세션을 넣고 도구가 꺼내 쓴다.
- **후보 단위 실행**: 에이전트 한 번 = 후보 하나. 도구에 `candidate_id` 인자를 두지 않는다. 잘못된 후보를 가리키는 호출을 없애기 위해서다.
- **동기 진입점**: NAT는 async다. `run_flow`는 동기를 유지하고 내부에서 이벤트 루프를 돌린다. 이미 루프가 도는 스레드에서 불리면 별도 스레드에서 실행한다.
- **모드 선택**: 환경변수 `LOGIC_AGENT_MODE=nat|rule`. Task 7(인계)부터 기본 `nat`. `LOGIC_AGENT_MODE=rule`로 이전 동작(고정 규칙 경로)을 그대로 되돌릴 수 있다.

## 5. 도구와 관문

| 도구 | 허용 조건 | 하는 일 (기존 메서드) | 종료 |
|---|---|---|---|
| `check_input` | 아직 검사 전 | `_check_input` → 문제 있으면 실패·보류 의견까지 기록 | 문제 있으면 종료(failed) |
| `lookup_public_structure` | 입력 통과, 조회 전 | `structures.find_structure` → 일치 여부·서열 길이를 사실 문장으로 반환 | |
| `use_experimental_structure` | 조회 완료, 완전 일치(`match.complete`) | `_record_experimental`, prediction `skipped` | |
| `predict_structure` | 조회 완료, 표적·중쇄·경쇄 모두 `MIN_CHAIN_LENGTH` 이상, 구조 미확보 | `_predict` (Boltz-2, 기존 재시도·한도 그대로) | 호출 실패면 종료(failed/partial, 현행 규칙) |
| `compare_structure` | 구조 확보, 비교 전 | `_compare` | |
| `submit_opinion(decision, reason)` | 비교 완료 | `_report`와 같은 의견 기록. `decision ∈ {reviewable, needs_confirmation}` | 종료(completed) |
| `hold_candidate(reason)` | 조회 완료, 구조 미확보, 완전 일치가 아님 (현행 `_choose_source`와 같은 조건) | `_hold_opinion`, 이후 단계 `skipped` | 종료(partial) |

규칙:
- 거부는 예외가 아니라 **거부 사유 문자열 반환**이다. 상태를 바꾸지 않고 세션의 거부 기록에 남긴다.
- 종료 뒤의 모든 호출은 거부한다. 종료 도구(`submit_opinion`·`hold_candidate`)는 NAT
  `return_direct`로 지정하지 않는다 — NAT의 `tool_conditional_edge`는 도구 이름만 보고
  END로 보내므로, 거부된 호출도 그 도구 이름이면 루프가 바로 끝나 버린다. 대신
  시스템 프롬프트에서 그 도구가 "검토를 끝냈다"고 답하면 한국어 한 문장으로 답하고
  더는 도구를 부르지 않게 지시해, 모델의 최종 답변으로 자연스럽게 끝나게 한다.
- `submit_opinion`·`hold_candidate`의 `reason`은 기존 `agent.invented_numbers`로 검사한다. 사실에 없는 숫자가 있으면 거부하고 다시 쓰게 한다.
- 도구가 반환하는 사실 문장은 기존 `_choose_source`·`_report`의 facts와 같은 문구를 쓴다. 이미 화면에서 교정한 문구다.
- 의견 기록의 판단 주체 표기는 현행 `(판단: <모델명>)`을 유지한다. 규칙으로 마무리한 부분은 `(판단: 규칙 — <이유>)`.

## 6. 끝나지 않을 때

| 상황 | 처리 |
|---|---|
| `max_iterations`(초기값 10) 도달 | 에이전트 중단 → 현재 상태부터 규칙으로 마무리, 사유 "에이전트 반복 상한" |
| 모델 호출 실패(503·timeout) | NAT 호출 오류 → 같은 방식으로 규칙 마무리, 사유에 오류 요약 |
| 종료 도구 없이 최종 답변만 냄 | 규칙 마무리 |
| NAT import 실패 | 실행 시작 시 `rule` 모드로 전환하고 결과 경고에 기록 |
| Nemotron 빈 응답("no content, no tool calls") | NAT 기본값 `max_empty_response_retries: 0`은 즉시 예외 → 규칙 마무리. §7 재측정 15회 중 4회가 이 원인이었다. `logic/nat_workflow.yml`의 `workflow.max_empty_response_retries`를 2로 올려 재시도하게 했다(이 변경 자체는 아직 재측정하지 않음) |

"규칙으로 이어서 마무리"는 새 함수 `_continue_by_rule(session)`이다. 세션 상태를 보고 남은 단계만 기존 규칙 경로로 실행한다. 이미 끝난 Boltz-2 호출을 다시 보내지 않는다.

## 7. 측정과 B 전환 기준

고정 시나리오 5개: trastuzumab(기존 구조), pertuzumab(기존 구조), 가상 변이체(예측), 잘못된 문자 입력, 50자 미만 서열. 각 3회 실행해 후보별로 기록한다: 도구 호출 수, 거부 수, 반복 상한 도달, 규칙 마무리 여부, 소요 시간, 최종 의견.

아래 중 하나면 B로 넘어간다. 수치는 **설계 제안**이며 측정 전에 조정할 수 있다.
1. 후보당 평균 거부 1회 초과
2. 반복 상한 도달이 15회 실행 중 1회 이상
3. 거부 때문에 `predict_structure`가 불필요하게 늦어져 시나리오 소요 시간이 규칙 모드 대비 2배 초과

0단계에서 스트리밍 + tool-calling이 안 되는 것으로 나오면 B로도 해결되지 않는다. 그때는 멈추고 보고한다(대안: NAT 비스트리밍 LLM 설정 여부 조사, 또는 C안 — 자체 루프 + NAT 추적).

### 측정 결과 (2026-09-26)

`uv run python -m logic.measure_agent --repeat 3` 1회 실행. 각 시나리오는 `LogicRequest`가 요구하는 후보 2건 이상 조건을 채우려고 입력 오류 필러 후보(`filler`)를 함께 넣었다 — 소요 시간에는 필러의 짧은 실행이 포함되지만, 아래 표의 호출 수·거부 수·상태·의견은 측정 대상 후보만 집계했다. 원본 기록: `work/measure-agent.jsonl`(gitignore 대상, 저장소에는 없음).

| 시나리오 | 규칙 모드 시간 | 에이전트 시간(3회) | 평균 거부 | 상한 도달 | 규칙 마무리 | 최종 상태·의견 |
|---|---|---|---|---|---|---|
| trastuzumab (기존 구조) | 22.3s | 31.7s / 25.5s / 24.4s | 1.00 (3/3회 각 1건) | 0/3 | 1/3 | 규칙: completed/needs_confirmation · 에이전트: completed/reviewable ×2, completed/needs_confirmation ×1 |
| pertuzumab (기존 구조) | 4.6s | 24.3s / 36.8s / 31.4s | 1.33 (1, 2, 1건) | 0/3 | 0/3 | 규칙: completed/needs_confirmation · 에이전트: completed/reviewable ×3 |
| variant (가상 변이체, 예측) | 10.7s | 27.6s / 51.2s / 16.3s | 1.33 (1, 2, 1건) | 0/3 | 0/3 | 규칙: failed/not_assessed · 에이전트: failed/not_assessed ×3 |
| invalid (잘못된 문자 입력) | 0.0s | 17.2s / 12.0s / 9.0s | 0.67 (1, 1, 0건) | 0/3 | 0/3 | 규칙: failed/hold · 에이전트: failed/hold ×3 |
| short (50자 미만 서열) | 2.4s | 10.0s / 5.8s / 11.4s | 0.00 (0, 0, 0건) | 0/3 | 0/3 | 규칙: partial/hold · 에이전트: partial/hold ×3 |

전체 nat 실행 15회(시나리오 5 × 3회) 기준 총 거부 13건, 반복 상한 도달 0건.

1. 후보당 평균 거부 1회 초과 → **비해당** (15회 실행 평균 0.87건 = 13건/15회, 1회를 넘지 않음)
2. 반복 상한 도달이 15회 실행 중 1회 이상 → **비해당** (0/15, `hit_limit`이 모든 행에서 false)
3. 거부 때문에 `predict_structure`가 불필요하게 늦어져 시나리오 소요 시간이 규칙 모드 대비 2배 초과 → **판정 보류** — variant는 규칙·에이전트 모든 실행에서 Boltz-2 호출이 실패해 예측 성공 경로를 측정하지 못했다; 시간 비율 2.96배는 거부 지연이 아니라 도구별 모델 호출 비용이 주된 차이로 보인다(거부로 predict_structure가 재호출된 실행은 3회 중 1회) — 원인 확인 후 재측정

A 유지 또는 B 전환 결정은 하지 않는다 — 사용자 확인 사항이다.

사용자 결정(2026-09-26): A 유지, 숫자 검사 오탐과 Boltz-2 실패를 고친 뒤 재측정.

### 재측정 결과 (2026-09-26, 6a·6b 수정 후)

`UV_LINK_MODE=copy uv run python -u -m logic.measure_agent --repeat 3` 1회 재실행. 6a(`invented_numbers`가 값을 비교하고 이미 보여준 사실을 누적하며 식별자 숫자를 무시)와 6b(variant 표적을 실제 1N8Z HER2 서열로, 변이 후보를 pertuzumab 중쇄 1자리 치환으로 교체)가 반영된 뒤의 실행이다. 첫 실행 원본은 `work/measure-agent-run1.jsonl`로 옮겨졌고, 이번 실행은 `work/measure-agent.jsonl`(gitignore 대상)에 새로 20줄 기록됐다. 콘솔 로그 원문: `.superpowers/sdd/nat-agent-loop-plan/measure-run2.log`.

| 시나리오 | 규칙 모드 시간 | 에이전트 시간(3회) | 평균 거부 | 상한 도달 | 규칙 마무리 | 최종 상태·의견 |
|---|---|---|---|---|---|---|
| trastuzumab (기존 구조) | 13.1s | 25.8s / 12.9s / 15.1s | 0.00 (0, 0, 0건) | 0/3 | 1/3 | 규칙: completed/needs_confirmation · 에이전트: completed/reviewable ×2, completed/needs_confirmation ×1 |
| pertuzumab (기존 구조) | 6.5s | 31.1s / 31.3s / 16.4s | 0.00 (0, 0, 0건) | 0/3 | 1/3 | 규칙: completed/needs_confirmation · 에이전트: completed/reviewable ×2, completed/needs_confirmation ×1 |
| variant (실제 1N8Z 표적, pertuzumab 1자리 변이) | 32.5s | 26.2s / 42.7s / 21.3s | 0.00 (0, 0, 0건) | 0/3 | 2/3 | 규칙: completed/reviewable · 에이전트: completed/needs_confirmation ×3 |
| invalid (잘못된 문자 입력) | 0.0s | 16.4s / 8.0s / 10.3s | 0.33 (0, 1, 0건) | 0/3 | 0/3 | 규칙: failed/hold · 에이전트: failed/hold ×3 |
| short (50자 미만 서열) | 14.5s | 11.1s / 52.7s / 18.9s | 0.00 (0, 0, 0건) | 0/3 | 0/3 | 규칙: partial/hold · 에이전트: partial/hold ×3 |

전체 nat 실행 15회(시나리오 5 × 3회) 기준 총 거부 1건, 반복 상한 도달 0건. 남은 거부 원인은 한 가지뿐이다 — invalid 시나리오 2회차에서 "거부: 이 후보의 검토는 이미 끝났다(failed). 더 부를 도구가 없다"(종료 후 도구 호출 시도, 1건). 6a가 고친 "확인된 사실에 없는 숫자" 사유의 거부는 이번 15회 중 0건이었다 — 첫 측정에서 13건이던 것과 대조된다.

참고(기준 판정에는 포함하지 않음): 이번 실행에서 `predict_structure` 자체는 3회 모두 한 번에 통과했지만, cand-v·cand-t·cand-p·filler 쪽에서 "LLM returned an empty response(no content, no tool calls)" 예외가 7회 발생했다. 이 예외가 나면 NAT 실행이 실패하고 규칙 마무리로 대체된다(`rule_finish=true`인 행들이 그 결과다) — 이는 거부(관문 검사 실패)가 아니라 Nemotron API 응답 자체가 비어 온 것으로, 이번 표의 "평균 거부"·기준 1·2 계산에는 포함하지 않았다.

1. 후보당 평균 거부 1회 초과 → **비해당** (15회 실행 평균 0.067건 = 1건/15회)
2. 반복 상한 도달이 15회 실행 중 1회 이상 → **비해당** (0/15, `hit_limit`이 모든 행에서 false)
3. 거부 때문에 `predict_structure`가 불필요하게 늦어져 시나리오 소요 시간이 규칙 모드 대비 2배 초과 → **비해당** — variant 시나리오의 nat 3회 모두 `predict_structure` 거부가 0건이었다(거부로 재호출된 적이 없음). 평균 소요 시간도 규칙 모드 32.5s 대비 에이전트 평균 30.07s(=(26.2+42.7+21.3)/3, 약 0.93배)로 오히려 더 느리지 않았다. 시나리오 간 시간 편차(예: short 3회차 52.7s)는 거부가 아니라 Nemotron 호출 자체의 지연(도구별 모델 호출 오버헤드)에서 온 것으로 보인다.


## 8. 로드맵

| 단계 | 내용 | 완료 확인 |
|---|---|---|
| 0 환경·전제 | `requires-python`을 `>=3.11,<3.14`로, `nvidia-nat[langchain]` 추가, `.venv`를 3.13으로 재생성. 더미 도구 하나로 NAT `tool_calling_agent` + Nemotron 실호출 | 도구가 실제 호출됨. 실패 시 중단·보고 |
| 1 세션·관문·도구 | `logic/nat_tools.py`(가칭): `CandidateSession`, `allowed_tools`, 도구 7개. NAT 없이 테스트 | 순서 위반 거부·종료 후 거부·숫자 검사 단위 테스트 통과 |
| 2 NAT 연결 | NAT 함수 등록, `logic/nat_workflow.yml`, `NatRunner`, 모드 스위치, 규칙 마무리 | 기존 테스트 전부 통과 + 모드별 결과가 `LogicOutput` 스키마 통과 |
| 3 측정 | 7절 시나리오 실행, 결과를 이 문서에 기록 | 표 채움. 실행하지 않은 값은 비워 둠 |
| 4 판단 | A 유지 또는 B 전환 결정 | 사용자 확인 |
| 4B (조건부) | `ToolCallAgentGraph` 하위 클래스로 허용 도구만 노출, 커스텀 워크플로 등록. 3단계 재측정 | 거부 0, 기준 재확인 |
| 5 인계 | `logic/README.md`, `logic-b-handoff.md`, D6(의존성·이미지 크기), ADR NAT 상태 갱신. 기본 모드를 `nat`으로 | **완료** — 서비스 담당이 읽고 실행 가능한 상태 |

## 9. 범위 밖

- 충돌·표면 노출 계산(로직 A의 A-02·A-03).
- 서비스 API·DB 변경. `run_flow` 계약을 바꾸지 않는다.
- `nat eval`·프로파일러 연동. 필요하면 5단계 이후 별도 작업.
- 여러 후보를 한 에이전트가 동시에 다루는 방식.
