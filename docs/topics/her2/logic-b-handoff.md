# 로직 B 인계 — 실행부 현재 상태와 D3–D6 초안

기준일 2026-09-25. 대상은 로직 A와 서비스 운영부다.
계획서 [B-01·B-03](../../plan.md#6-로직-b-계획--외부-예측과-에이전트-흐름)의 인계 항목을
**실제로 구현·실행한 범위만** 적는다. 코드 사용법은 [logic/README.md](../../../logic/README.md)에 있다.

## 1. 지금 무엇이 되는가

| 계획 항목 | 상태 | 근거 |
|---|---|---|
| B-03 기존 구조 경로 | **동작** | trastuzumab·pertuzumab 입력 → 두 후보 완료, 접촉 잔기 39·56건 |
| B-03 보류·입력 오류 분기 | **동작** | 테스트 31건 통과 (`python -m pytest logic/tests -q`) |
| B-01 계정·실제 호출 | **미확인** | `NVIDIA_API_KEY` 미발급. 실제 호출 0건 |
| B-02 HER2 예측 연결 | **미확인** | 코드는 있으나 대역 client로만 실행 |
| B-04 장애·한도·재현성 | **부분** | 실패·timeout 분기는 테스트로만. 실측 한도 없음 |

예측 경로는 키가 생기면 `python -m logic.check_key` → 실제 요청 순으로 확인한다.
`logic/call_log.jsonl`에 실제 기록이 남기 전까지 B-01·B-02를 완료로 적지 않는다.

## 2. D4 실행 계약 — 서비스 ↔ B

B는 **HTTP·DB를 모른다.** 작업 점유·재시작·중복 접수·상태 보존은 운영부 몫이다.

진입점 두 가지 중 하나를 쓴다.

```bash
python -m logic.run --request req.json --out out.json --progress progress.jsonl
```

```python
from logic.flow import run_flow
output, flow = run_flow(request_dict, progress=on_progress)
```

- 입력 `LogicRequest`, 출력 `LogicOutput`. 필드 정의 원본은
  [service.schema.json](../../frontend-hosting/contracts/service.schema.json)이며 B는 복제하지 않고 읽어서 검증한다.
- 진행 이벤트는 `ProgressUpdate` JSON 한 줄씩. `--progress` 파일에 append 되고 동시에 stderr로 나간다.
- 계약 위반 입력은 **실행하지 않고** 종료 코드 `2`. 그 외에는 `0`.
- 후보별 보류·실패는 종료 코드가 아니라 결과 안에서 구분한다. 종료 코드 0을 "전부 성공"으로 읽지 않는다.

단계 ID 다섯 개는 계약의 `step_id`를 그대로 쓴다:
`input_mapping` · `evidence_review` · `prediction` · `structure_comparison` · `reporting`.

**재시작·중복 호출:** B는 멱등성을 보장하지 않는다. 같은 요청을 두 번 주면 외부 호출도 두 번 나간다.
중복 방지는 운영부가 작업 점유로 막는다 (B-04에서 재확인 필요).

## 3. D5 결과 계약 — B → 서비스

`LogicOutput = { result: Result, files: [OutputFile] }`.

`Result`가 담는 것: `schema_version` · `data_mode` · `run_id` · `review_id` · `candidate_ids` ·
`created_at` · `settings_version` · `structures` · `conditions` · `evidence` · `opinions` · `artifacts`.

`Run.status` 판정:

| 후보 상태 | `run_status()` |
|---|---|
| 전부 `completed` | `completed` |
| 하나라도 `completed`/`partial` 포함 | `partial` |
| 그 외 | `failed` |

**미확인과 0의 구분**은 `measurement_state`로 한다: `measured` · `unknown` · `not_applicable` ·
`not_run` · `failed`. `measured`가 아닌 근거는 스키마가 `value: null` + `reason`을 **강제**한다.
화면에서 `not_run`을 0으로 표시하지 않는다.

현재 `not_run`으로 나가는 항목: `atom_clash`, `surface_exposure`.
A-02·A-03의 계산 함수가 들어오면 [logic/analysis.py](../../../logic/analysis.py)의 자리에 연결한다.

## 4. D3 예측 결과 — B → A

**아직 실제 응답이 없다.** 구현된 것은 요청 조립·응답 파싱·`call_log.jsonl` 기록까지다.

- 호출 대상: `https://health.api.nvidia.com/v1/biology/mit/boltz2/predict`
- 반환 구조는 `kind: "predicted"`로 `structures`에 들어가고 신뢰도는 `evidence`로 분리한다.
- 반환되지 않은 지표는 채우지 않고 `not_run`으로 남긴다.

A가 확인해야 할 것: 실제 응답의 사슬·잔기 번호가 입력 후보와 대응하는지.
[확인 필요: 실제 Boltz-2 응답의 사슬 ID 규칙과 MSA 경로 요구 여부 — 키 발급 후]

## 5. D6 배포 인계 초안

| 항목 | 값 | 확인 방법 |
|---|---|---|
| Python | 3.13.9 | 실행 환경에서 확인 |
| 외부 라이브러리 | `jsonschema` 4.26.0, `requests` 2.32.5 | 실제 import 목록 기준 |
| 그 외 import | 표준 라이브러리만 | `logic/*.py` import 전수 확인 |
| 환경변수 | `NVIDIA_API_KEY` (대안 `NGC_API_KEY`), `NEMOTRON_MODEL` | `logic/env.py` |
| 외부 통신 | `health.api.nvidia.com`, `integrate.api.nvidia.com` | `logic/nvidia_client.py` |
| 호출 timeout | 기본 600초 | `DEFAULT_TIMEOUT` |
| 작업 디렉터리 | `NvidiaClient(work_dir)`에 쓰기 권한 필요 (`call_log.jsonl`) | — |
| GPU | 불필요 (예측은 원격 NIM) | — |
| 실제 소요 시간·메모리·파일 용량 | [확인 필요: 실제 호출 후 측정 — B-02] | — |

B는 **Biopython·freesasa를 쓰지 않는다.** 그 의존성은 로직 A 쪽에서 나온다.

## 6. 미확인·결정 필요

- **실제 NVIDIA 호출 0건.** 키 미발급. 예측 경로는 대역 client 검증뿐이다.
- 접촉 잔기는 `contacts.json`의 4.5 Å 근접 선택이다. 그 생성 스크립트 자체가
  `Not binding assessment`라고 적고 있다. **결합력·효능 근거로 쓰지 않는다.**
- 잔기 번호는 `auth_chains=False`로 만들어져 **label** 기준이다. `auth_seq_id`는 `null`이다.
  대응 확인 전에 3D 화면 강조에 그대로 넘기면 안 된다. → **A의 D2에서 대응표 필요**
- `residue_mapping`·`alignment`는 비어 있다. A의 D2 인계 후 채운다.
- 모든 후보가 보류된 실행의 `Run.status`. 계약 enum에 `held`가 없어 현재 `partial`로 둔다.
  → **G1에서 서비스와 합의 필요**
- `MIN_CHAIN_LENGTH`(50)와 접촉 거리 4.5 Å은 형식 하한·선택 기준이며 과학적 판정 기준이 아니다.
  → **PRD Q05**

## 7. 받는 쪽이 할 일

**서비스(S-02):** 2절의 진입점을 호출하고 `ProgressUpdate` 줄을 상태로 옮긴다.
종료 코드 0 ≠ 전부 성공임을 반영한다. 3절 `measurement_state`를 화면 표기에 연결한다.

**로직 A(A-02):** `logic/analysis.py`의 `Measurement` 형태로 충돌·표면 노출 계산을 넘긴다.
label ↔ auth 잔기 번호 대응표를 D2로 준다.
