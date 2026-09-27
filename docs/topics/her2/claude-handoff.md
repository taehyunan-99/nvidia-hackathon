# Claude 인계 — HER2 에이전트 실측 및 개선

2026-09-27 KST. 사용자 요청은 **구현된 에이전트를 실제 데이터로 성능 검증하고 개선한 뒤 정직하게 보고하는 것**이다.
이 문서를 읽고 현재 변경을 리뷰한 뒤 남은 성능 문제를 이어서 해결하라. 작업 완료 사실과 과학적 정확도를 구분하라.

## 작업 위치와 보존할 상태

- 작업 디렉터리: `/Volumes/Extreme SSD/nvidia/agent-performance`
- 브랜치: `fix/agent-performance`, 시작 커밋 `0691dc8` (`feat/judgment-scoring` 기반).
- **모든 변경은 미커밋이다.** 커밋·push·PR 수정·병합은 하지 않았다. 변경을 다른 브랜치에서 찾지 말 것.
- 본체: `/Volumes/Extreme SSD/nvidia/nvidia-hackathon`
- Python: `/Volumes/Extreme SSD/nvidia/nvidia-hackathon/.venv/bin/python`
- 실제 호출용 환경 파일: 본체의 `.env`. `logic.env.load_env(Path(...))`로 읽으며 값을 출력하지 말 것.
- 이 worktree의 `work/agent-benchmark/`에 원시 응답, 실험 구조, 실행 로그가 있다. 무시되는 로컬 파일이므로
  새 worktree를 만들거나 브랜치만 checkout하면 따라오지 않는다. **현재 디렉터리를 그대로 이어받는 것이 안전하다.**
- 다른 Claude worktree (`.claude/worktrees/goldset-scoring`, `.claude/worktrees/fix-agent-m1-m2`)는 건드리지 않았다.
- 루트 `AGENTS.md`, `CONTRIBUTING.md`, 문서 작업 시 하위 `AGENTS.md`를 따른다. README는 의도적으로 비어 있다.

## 먼저 읽을 근거

1. [최종 벤치마크 보고서](agent-benchmark-report.md) — 수정 전/후 실제 결과와 한계.
2. [예측·파서 검증](agent-performance-validation.md) — 기존 주장 재검증, 샘플 수 비교.
3. `logic/nat_model.py`, `logic/nat_agent.py`, `logic/nat_workflow.yml` — 최근 429 대응.
4. `logic/contacts.py`, `logic/flow.py`, `logic/agent_session.py` — 파서, 예측 선택, 실패·판정 처리.
5. `docs/topics/her2/assets/goldset/generated/`의 `agent-benchmark-*`, `paced-agent-*` — 고정 입력·코드 해시·실측 결과.

## 실제 성과와 남은 실패

### 에이전트 완주: 개선 확인

8사례 중 입력 오류 2건은 코드로 거부하므로 모델 평가 분모는 6건이다.

| 지표 | 수정 전 | 429 대응 후 |
|---|---:|---:|
| 권장 경로를 선택하고 규칙 대체 없이 의견/보류 제출 | 2/6 | 6/6 |
| 규칙으로 대체 | 4/6 | 0/6 |
| 미처리 오류 없이 전체 종료 | 1/6 | 6/6 |

수정 후 실제 HTTP는 **200 25회, 429 7회**, 429 모두 다음 시도에서 회복했다.
HTTP 오류 자체가 한 번도 없었던 모델 사례는 **1/6**뿐이다. `clean_success`는 복구된 HTTP 오류까지
없다는 뜻이 아니다. 최소 요청 간격 15.000589초, 승인된 제출 후 생략한 LLM 요청 6회.
소요 시간 31.015~147.740초. 새 Boltz 호출 0회, 이전 실제 응답 캐시 2회 사용.
입력 오류 2건은 HTTP 0회로 차단했고 최종 출력 기대값은 8/8 일치했다.

같은 사례의 회귀 시험이지 새로운 독립 표본이 아니다. 전후 시간이 달라 서버 상태 변화도 섞일 수 있다.
따라서 일반 성공률 100%, 순수 모델 지능 향상, 429 완전 해결로 주장하면 안 된다.

### 구조 정확도: 여전히 실패

개발에 사용하지 않았던 공개 실험 구조 8JYR(H2Mab-119), 3N85(Fab37)의 서열로 실제 Boltz를 호출했다.
원래 시험에서 각각 1회 호출했고 이번 429 시험은 그 응답을 그대로 재사용했다.

| 구조 | 실험 표적 접촉 | 예측 표적 접촉 | 겹침 | F1 |
|---|---:|---:|---:|---:|
| 8JYR | 19 | 14 | 0 | 0 |
| 3N85 | 27 | 22 | 0 | 0 |

실험 좌표와 예측 좌표 모두 별도 brute-force 계산기로 제품 접촉 알고리즘과 일치함을 확인했다.
파싱 실패를 F1=0으로 잘못 센 것이 아니다. 신뢰도는 각각 약 0.882, 0.846으로 높아도 접촉은 틀렸다.
접촉 F1은 표적 잔기 집합의 구조 지표다. 결합력·치료 효능 지표가 아니다.
개발 미사용이라는 뜻이며 모델 학습 데이터에서 제외됐다는 뜻은 아니다.

## 구현 변경

- `contacts.py`: 수동 줄 파싱을 설치된 gemmi CIF 파싱으로 교체. 여러 줄 atom record를 놓치던 버그 수정.
  실제 저장 파일에서 1S78 0→8149 원자, OpenFold 0→7969 원자로 복구.
- `flow.py`: 비어 있지 않은 구조 중 유효한 [0,1] 신뢰도가 가장 높은 것을 선택하고 해당 점수를 함께 기록.
  신뢰도 배열 불일치·잘못된 값은 미상 처리. **diffusion_samples 기본값은 여전히 1**.
- `agent_session.py`: 유료 예측 후 후처리 실패 시 상태를 복구하고 terminal 실패로 만들어 중복 유료 호출 방지.
  미계산 근거가 남거나 측정 근거가 없으면 reviewable 제출 거부. 규칙 경로도 같은 보수적 판정.
- `nat_agent.py`: 입력 검사를 LLM 전에 코드로 수행. 잘못된 입력에 모델 호출하지 않음.
- `flow.py`/`measure_agent.py`: 제출 후 오류도 `agent_errors`에 보존. 단, 새 어댑터에서 복구된 429는
  `agent_errors`까지 올라가지 않으므로 `measure_agent.rate_limited`만 보면 과소계수할 수 있다.
  최근 재시험은 `nim_http` 로그를 별도로 집계해 이 오류를 피했다. 향후 일반 측정기도 이 구분을 유지할 것.
- `nat_model.py`: NAT 커스텀 NIM adapter. 프로세스 공용 요청 간격 15초, 429 최대 총 3시도,
  30/60초와 Retry-After 중 긴 시간 적용. 120초 초과 요구/부분 응답 수신 시 재시도하지 않음.
  승인된 session.terminal에만 고정 종료 문장으로 불필요한 마지막 HTTP 생략; 제출 거부는 계속 모델 호출.
  상태·시각·허용된 응답 헤더만 기록. 다른 프로세스/계정 사용자까지 속도 제어하지는 못함.
- `nat_workflow.yml`: `her2_paced_nim`, 모델 `nvidia/nemotron-3-super-120b-a12b`, temp0,
  max_tokens1024, max_iterations10, 빈 응답 재시도2. `return_direct`는 넣지 않았다.

## 버린 결론/접근

- “diffusion_samples=5면 해결”: 1N8Z는 1개/5개 모두 F1 .884. 1S78은 1개 .041,
  5개 중 신뢰도 선택 .000, 정답을 보고 고른 최고값 .286. 일반화 못하므로 기본값을 올리지 않았다.
- “6BGT F1 .923은 천장”: 특정 기준 구조 간 유사도일 뿐 이론적 천장이 아니다.
- “OpenFold 접촉0, 복합체 실패”: 파서 오류였음. 재채점 표적 접촉21, 적중2, F1 .100.
- “세션이 달라져서 복권”: 과거 요청은 체인 순서/ID도 달랐다. 원인 분리 없이 결정론을 단정하지 말 것.
- 과거 `boltz2_response.json` 중 구조가 `<785544 chars>` 같은 문자열로 대체된 자료는 재채점 불가.
- 후보 사이 90초 대기만으로 내부 연속 요청을 제한하지 못했다. 현재는 실제 요청별 제한.
- `return_direct`로 종료 도구를 무조건 끝내면 거부된 제출도 조기 종료된다. 승인된 terminal만 종료해야 한다.

## 다음 작업 우선순위와 완료 기준

1. 현재 diff를 리뷰하고 기존 실측 산출물·코드 해시·테스트 결과를 확인한다. 무작정 유료 재실행하지 않는다.
2. 처리량/관측 개선: 복구된 429·빈 응답·미처리 오류를 구분한다. 필요 시 간격을 조정하되
   기존 회차를 덮어쓰지 말고 새 회차로 비교한다. 서버는 수집 대상 제한 헤더를 보내지 않아 정확한 한도는 미상.
3. 핵심 남은 문제는 새 항체의 구조 접촉 정확도다. 소수 성공 예시나 신뢰도 수치만으로 개선을 선언하지 않는다.
   개발용 사례와 별도 평가 사례를 나누고 같은 입력의 실제 예측을 독립 구조 기준으로 채점한다.
4. `lookup_public_structure`는 현재 1N8Z/1S78 로컬 카탈로그 조회다. 인터넷 전체 탐색이 아니다.
   공개 구조 조회 확대, 미구현 atom_clash/surface_exposure 연결은 별도 후보 과제다. 사용자 목적에 맞게 좁혀서 진행한다.
5. 보고 시 모델 직접 완료율, 규칙 대체율, HTTP 복구/실패, 시간/호출량, 구조 정확도를 각각 제시한다.

## 재현 명령 (현재 worktree에서)

```sh
cd '/Volumes/Extreme SSD/nvidia/agent-performance'
../nvidia-hackathon/.venv/bin/python -m pytest -q
../nvidia-hackathon/.venv/bin/python docs/topics/her2/assets/goldset/benchmark_agent.py self-test
../nvidia-hackathon/.venv/bin/python docs/topics/her2/assets/goldset/summarize_agent_benchmark.py
../nvidia-hackathon/.venv/bin/python docs/topics/her2/assets/goldset/summarize_paced_agent.py
git diff --check
```

최종 전체 검사: **156 passed, 18 skipped**. live 생략을 실제 API 성공으로 세지 않았다.
실제 API 시험은 별도 위 8사례 기록이다. 제품 코드 고정 해시와 재사용 구조 2개의 해시를 검사했다.
`check_paced_agent.py`는 실제 Nemotron 호출 스크립트이며 이미 결과가 있어 재실행을 거부한다.
이 보호를 지우지 말고 새 실험은 명시적으로 별도 회차에 기록한다.

## 인계 제약

사용자는 원인 설명만 반복하거나 작업을 멈추는 것을 원하지 않는다. 승인된 범위에서 실제 작업까지 완료하라.
이 대화에서 사용자는 실제 성능 테스트와 429 복구 후 8사례 재시험을 승인했다. 새 비용이 큰 실험은
범위와 비용을 구분하고 무제한 반복하지 말 것. 원래 결과를 성공으로 덮어쓰지 말 것.
커밋·push·병합은 별도 명시 요청 없이 하지 않는다. 자격 증명·프롬프트를 진단 로그에 무분별하게 출력하지 않는다.
