# 로직 B — 판단 흐름과 NVIDIA 호출

계획서의 [B-01·B-03](../docs/plan.md#6-로직-b-계획--외부-예측과-에이전트-흐름) 범위다.
서비스 운영부에서 `LogicRequest`를 받아 후보별 분석을 실행하고 `LogicOutput`을 돌려준다.
필드 정의 원본은 [service.schema.json](../docs/frontend-hosting/contracts/service.schema.json)이며
이 코드는 스키마를 복제하지 않고 읽어서 검증한다.

## 키 설정

```bash
cp .env.example .env     # 저장소 루트
# .env의 NVIDIA_API_KEY= 뒤에 발급받은 키를 붙여넣는다
python -m logic.check_key
```

키는 <https://build.nvidia.com/settings/api-keys>에서 로그인 후 발급한다.
`.env`는 `.gitignore`가 막고 있고 `.env.example`만 공유된다(테스트가 git에 직접 확인한다).
팀원마다 각자 키를 쓰며 채팅·이슈·커밋에 값을 넣지 않는다.
`logic.env.mask()`를 거치지 않은 키는 어떤 로그에도 남기지 않는다.

## 실행

```bash
python -m logic.run --request req.json --out out.json --progress progress.jsonl
```

```bash
python -m pytest logic/tests -q
```

## 구성

| 파일 | 역할 |
|---|---|
| `contract.py` | 임시 계약 로딩·검증. 생산한 객체는 전부 스키마로 확인한 뒤 내보낸다 |
| `structures.py` | 공개 실험 구조 조회와 후보 대응. mmCIF `_entity_poly` 파서 포함 |
| `nvidia_client.py` | Boltz-2·Nemotron 호출. 요청 요약·응답·소요 시간을 `call_log.jsonl`에 남긴다 |
| `analysis.py` | 계산 결과를 Evidence 재료로 변환. 로직 A의 함수가 들어올 자리 |
| `flow.py` | 다섯 단계와 분기 |
| `run.py` | 실행부 진입점 (D4의 B쪽) |

## 단계와 분기

단계 ID는 계약의 `step_id`를 그대로 쓴다.

| step_id | 설계 문서의 단계 |
|---|---|
| `input_mapping` | 입력 검사·공개 자료 조회 |
| `evidence_review` | 사슬 번호 확인 및 구조 검사 |
| `prediction` | Boltz-2 복합체 예측 (기존 구조가 있으면 `skipped`) |
| `structure_comparison` | 접촉 부위·구조상 문제 계산 |
| `reporting` | 후보 비교·근거 설명 |

분기 판정:

- **기존 구조 확보** — 중쇄·경쇄 서열이 공개 구조의 사슬과 **정확히** 일치하고 같은 구조에 표적 사슬이 있을 때만. 한쪽 사슬만 맞으면 같은 후보로 보지 않고 예측 경로로 보낸다.
- **예측** — 표적·중쇄·경쇄가 모두 `MIN_CHAIN_LENGTH`(50) 이상일 때만 호출한다. 형식 오류를 예측 호출로 넘기지 않기 위한 하한이며 과학적 기준이 아니다.
- **자료 부족 보류** — 위 조건을 못 채우면 호출하지 않고 `held`로 남긴다.

## 실행으로 확인한 것

2026-09-25 기준.

- 1N8Z·1S78 mmCIF 파싱과 `verified-structures.json`의 sha256 일치 — 두 파일 모두 확인.
- trastuzumab·pertuzumab 실제 서열 입력 → 두 후보 모두 예측 생략, 접촉 잔기 39·56건.
  이 수는 `contacts.json`을 직접 읽어 대조한다(`test_contact_evidence_matches_precomputed_file`).
- 입력 오류·자료 부족·호출 실패·구조 없는 응답·키 없음 분기 — 테스트 16건 통과.

## 아직 확인하지 않은 것

- **실제 NVIDIA 호출은 한 번도 하지 않았다.** `NVIDIA_API_KEY`가 없어 예측 경로는 대역 client로만 확인했다. `call_log.jsonl`에 실제 기록이 남기 전까지 B-01·B-02를 완료로 표시하지 않는다.
- 접촉 잔기는 `contacts.json`의 4.5 Å 근접 선택이다. 그 생성 스크립트 자체가 `Not binding assessment`라고 적고 있으므로 결합력·효능 근거로 쓰지 않는다.
- 충돌·표면 노출은 `not_run`이다. 기준 확정과 계산 함수는 로직 A(A-02·A-03)의 인계를 기다린다.
- 잔기 번호는 `contacts.json`이 `auth_chains=False`로 만들어져 **label** 기준이다. `auth_seq_id`는 `null`로 두었고 대응 확인 전에는 화면 강조에 그대로 쓰면 안 된다.
- `residue_mapping`과 `alignment`는 비어 있다. A의 D2 인계 후 채운다.

## 확인이 필요한 결정

- 모든 후보가 보류된 실행의 `Run.status`. 계약의 enum에 `held`가 없어 현재 `partial`로 둔다. G1에서 서비스와 맞춘다.
- `MIN_CHAIN_LENGTH`와 접촉 거리 4.5 Å을 판정 기준으로 확정할지 (PRD Q05).
