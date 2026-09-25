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
| `contacts.py` | 좌표에서 접촉 잔기 직접 선택. 예측 구조용이며 기준은 실험 구조 쪽과 같다 |
| `analysis.py` | 계산 결과를 Evidence 재료로 변환. 로직 A의 함수가 들어올 자리 |
| `agent.py` | 분기를 Nemotron에게 묻는 판단부. 선택지 밖 답·지어낸 숫자를 거르고, 못 쓰면 규칙으로 돌아간다 |
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

2026-09-26 기준.

- 1N8Z·1S78 mmCIF 파싱과 `verified-structures.json`의 sha256 일치 — 두 파일 모두 확인.
- `contacts.py`의 접촉 잔기 선택이 팀이 Biopython으로 만든 `contacts.json`과
  **잔기 집합까지 완전히 일치**한다(1N8Z 39건·1S78 56건). 개수만이 아니라 어느
  잔기인지까지 대조한다(`test_matches_the_biopython_selection_exactly`).
- trastuzumab·pertuzumab 실제 서열 입력 → 두 후보 모두 예측 생략, 접촉 잔기 39·56건.
  이 수는 `contacts.json`을 직접 읽어 대조한다(`test_contact_evidence_matches_precomputed_file`).
- 입력 오류·자료 부족·호출 실패·구조 없는 응답·키 없음 분기 — 테스트 통과.

### 판단부 (2026-09-26 실측)

설계 문서는 "Nemotron이 상태에 따른 작업 선택과 결과 설명을 맡는다"이고
"단계가 고정 파이프라인이 되지 않게 할 분기"를 따로 두고 있다. 그 자리를
`agent.py`가 채운다. 두 분기를 모델이 고른다 — 검토할 구조를 어디서 얻을지
(`structure_source`), 지금 검토 의견을 낼 수 있는지(`review_opinion`).

모델에게 허용하는 것은 **주어진 목록에서 고르기와 이유 쓰기**뿐이다.
접촉 잔기 수·신뢰도·서열 길이는 전부 코드가 계산해 사실로 넣어 준다.

| 거르는 것 | 방법 |
|---|---|
| 목록에 없는 행동 | 버리고 규칙으로 |
| 근거에 없는 숫자를 쓴 설명 | 고른 행동까지 통째로 버린다 |
| 모델 호출 실패·형식 위반 | 규칙으로 가되 "규칙으로 갔다"를 화면 문구에 남긴다 |

**쓸 수 있는 모델이 사실상 하나다.** 목록에 nemotron 계열 17개가 보이지만
대부분 이 계정에서 404다.

| 모델 | 결과 |
|---|---|
| `nvidia/nemotron-3-super-120b-a12b` | 성공, 6.2초 — 현재 기본값 |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 성공, 60.6초, 사고 과정이 답변에 섞임 |
| `nvidia/nemotron-nano-3-30b-a3b`, `llama-3.1-nemotron-70b/51b-instruct` | HTTP 404 |
| `nvidia/nemotron-3-nano-30b-a3b` (설계 문서가 고른 것) | 목록에 없음 |

실제 실행(후보 2건, 판단 4회): 전체 **57.1초**. 이 중 한 번은 모델이
HTTP 503(Service temporarily overloaded)을 돌려줬고 재시도 3회가 모두
실패해 규칙으로 넘어갔다. **판단 호출은 예측 호출만큼 안정적이지 않다.**
같은 실행에서 모델은 두 후보 모두 `needs_confirmation`을 골랐다 —
충돌·표면 노출이 미계산이라는 이유다. 규칙은 같은 자리에서
`reviewable`을 골랐을 것이다. 즉 판단부는 장식이 아니라 결과를 바꾼다.

### 실제 NVIDIA 호출 (대역 client 아님)

- `list_models` 성공 — 모델 82개, nemotron 계열 17개.
- Boltz-2 소형 입력(65잔기, recycling 1·sampling 10) — **5.5초**.
- Boltz-2 HER2 복합체(표적 607 + 중쇄 226 + 경쇄 214 = 1,047잔기, 기본 설정
  recycling 3·sampling 50·samples 1) — **12.0초**, 응답 mmCIF **791,331 bytes**,
  `confidence_scores[0] = 0.807`.
- 반환 구조의 세 사슬 서열이 입력 세 서열과 **완전 일치**함을 파일에서 직접 읽어 대조했다.
- 예측 구조의 접촉 잔기를 좌표에서 직접 계산했다. 변이체 후보 39건, 표적 쪽은
  잔기 13–135·330–391. 같은 실행의 trastuzumab(실험 구조)은 557–605로
  **표적 잔기가 하나도 겹치지 않는다.** 두 후보가 다른 부위에 닿는다는 뜻이다.

이 호출로 드러나 고친 것 두 가지:

1. `_read_loop`가 loop 안의 빈 줄을 끝으로 판단했다. 공개 구조 파일에는 빈 줄이
   없고 Boltz-2 응답에는 있어서, 예측 구조의 사슬이 통째로 안 읽혔다.
2. `chain_mapping`이 요청에 보낸 사슬 id(A·H·L)를 그대로 적었다. Boltz-2는
   순서대로 A·B·C로 다시 붙인다. 이제 응답 파일의 서열로 대응을 찾고, 못 찾으면
   지어내지 않고 `null`로 둔다.

둘 다 회귀 테스트가 있다(`test_structures.py`, `test_predicted_chain_mapping_uses_ids_from_the_response`).
fixture `logic/tests/fixtures/boltz2-response-excerpt.cif`는 실제 응답에서 발췌한 것이다.

### 호출 한도 (실측 2026-09-26)

**공식 수치는 얻지 못했다.** 응답 어디에도 한도 헤더가 없다 — `X-RateLimit-*`도,
429의 `Retry-After`도 없다. 아래는 전부 직접 불러 본 관측이며 공식 문서 근거가
아니다. [확인 필요: build.nvidia.com 로그인 후 공식 한도]

| 방식 | 결과 |
|---|---|
| 동시 20건 (한가한 상태에서) | 200 **10건** / 429 10건 |
| 동시 12건 (직후 연달아) | 200 2건 / 429 10건 |
| 순차 6건, 서로 다른 입력 | 200 4건 / **429 2건** |
| 순차 8건, 같은 입력 | 200 8건 (3번째부터 1.1초 — 캐시로 의심) |
| 16스레드로 계속 부하 | 200 1건 / 429 787건 |
| 포화 후 회복 | 약 15초 뒤 재시도 성공 |

읽을 것은 두 가지다.

1. **순차 호출에서도 429가 난다.** 우리 흐름은 한 번에 한 건씩 부르는데도 6건 중
   2건이 막혔다. "동시에 안 부르니 안전하다"는 말은 틀렸다.
2. 429는 **즉시(0.2초)** 돌아오고 대기 시간을 알려주지 않는다. 받는 쪽이 간격을
   정해야 한다.

그래서 `nvidia_client._post`에 429·503 재시도를 넣었다 (5·10·20초, 최대 3회).
`Retry-After`를 주면 그쪽을 따른다. **재시도로 성공해도 429를 기록에서 지우지
않는다** — 지우면 나중에 시연이 왜 느렸는지 알 수 없다.

부하를 계속 거는 상태에서 실제로 확인했다: 재시도 3회 후 중단하고,
`call_log.jsonl`에 429 네 건이 모두 남았다.

## 아직 확인하지 않은 것

- 예측 경로를 **한 조합으로만** 확인했다. 다른 후보·길이·`diffusion_samples > 1`은 미확인이다.
- 한도의 **공식 수치**는 모른다. 위 표는 관측이지 계약이 아니며 계정·시간대에 따라 다를 수 있다.
- 접촉 잔기는 `contacts.json`의 4.5 Å 근접 선택이다. 그 생성 스크립트 자체가 `Not binding assessment`라고 적고 있으므로 결합력·효능 근거로 쓰지 않는다.
- 예측 구조의 **충돌** 계산은 아직 없다. 접촉 잔기는 계산한다.
- 충돌·표면 노출은 `not_run`이다. 기준 확정과 계산 함수는 로직 A(A-02·A-03)의 인계를 기다린다.
- 잔기 번호는 `contacts.json`이 `auth_chains=False`로 만들어져 **label** 기준이다. `auth_seq_id`는 `null`로 두었고 대응 확인 전에는 화면 강조에 그대로 쓰면 안 된다.
- `residue_mapping`과 `alignment`는 비어 있다. A의 D2 인계 후 채운다.

## 확인이 필요한 결정

- 모든 후보가 보류된 실행의 `Run.status`. 계약의 enum에 `held`가 없어 현재 `partial`로 둔다. G1에서 서비스와 맞춘다.
- `MIN_CHAIN_LENGTH`와 접촉 거리 4.5 Å을 판정 기준으로 확정할지 (PRD Q05).
