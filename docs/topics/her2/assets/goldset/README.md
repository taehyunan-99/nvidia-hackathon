# 판단 채점용 평가셋 (goldset)

> [기준 계면 겹침 검산](../../agent-benchmark-report.md): `check_epitope_overlap.py`가 캐시된 예측 4건으로
> `predicted_epitope_overlap_with_reference` 근거를 검산한다. API를 부르지 않는다.
> 결과는 `generated/epitope-overlap-check.json`이다.
>
> [후속 재검증](../../agent-performance-validation.md): mmCIF 파싱 오류를 수정했다.
> 5샘플의 일반적인 우위와 0.923 상한 해석은 확인되지 않았다. 원본 보존·제품 코드 선택 검증은
> `verify_prediction.py`를 사용한다. `generated/verified-*.json`이 수정 후 결과다.
>
> [샘플 간 일치도](../../agent-performance-validation.md): `check_sample_agreement.py`가 캐시된
> 5샘플 응답 2건으로 샘플끼리 같은 자리에 붙는지 잰다. API를 부르지 않는다. 맞은 사례와
> 틀린 사례가 갈리지 않아 **지표로 쓰지 않는다**. 결과는 `generated/sample-agreement-check.json`이다.

에이전트가 내리는 판단을 **실제 결정 구조에 대고 채점**하기 위한 자료와 도구다.
만든 날 2026-09-26. 배경과 결과 해석은 [judgment-scoring.md](../../judgment-scoring.md)에 있다.

## 왜 만들었나

`nat-agent-loop.md` §7의 "규칙 모드 대 에이전트" 표는 판단 정확도의 근거가 되지 못한다.

- `logic/agent.py`의 `Decider.choose`는 규칙 모드에서도 Nemotron에게 물어본다.
  코드에 박힌 `default`는 모델을 **못 부를 때만** 쓰는 값이다. 두 열은 같은 모델을
  한 번에 묻느냐 도구 루프로 묻느냐의 차이이고, 어느 쪽도 정답이 아니다.
- `logic/analysis.py`의 `pending_measurements`는 `atom_clash`·`surface_exposure`를
  **항상** `not_run`으로 돌려준다. 그래서 `flow.py`의 기본값은 현재 구현에서
  언제나 `needs_confirmation`이다. 판별력이 0이다.

`reviewable`/`needs_confirmation`의 정답 기준은 아직 미정이다
(`validation.md`가 "독립적인 정답 기준"을 미결정 항목으로 적어 두었다).
그래서 **정답이 분명한 다른 지점**을 골라 채점 기준을 만들었다.

## 평가셋 — 실제 PDB 10건

RCSB 검색으로 HER2 항체 복합체를 찾아, 이미 쓰는 1N8Z·1S78을 뺀 10건을 모았다.

| PDB | 표적 | 항체 | 쓰임 |
|---|---|---|---|
| 3BE1 | HER2 | bH1 (트라스투주맙 골격 이중특이) | 같은 에피토프 양성 |
| 3WSQ | HER2 | 미상 Fab | 다른 에피토프 |
| 5O4G | HER2 | MF3958 | 다른 에피토프 |
| 6ATT | HER2 | 39S | 다른 에피토프 |
| 6BGT | HER2 | 트라스투주맙 변이체 | 변이체 양성 |
| 9L1S | HER2 | 퍼투주맙 T30S/D31A 변이체 | 변이체 양성 |
| 9T3R | HER2 | EPS232 | 부분 겹침 |
| 9T3S | HER2 | EPS226 | 부분 겹침 |
| 4P59 | **HER3** | MOR09825 | 틀린 표적 음성 대조 |
| 8YRY | **HER3** | Hu3f8 | 틀린 표적 음성 대조 |

6BGT·9L1S는 측정기의 가상 변이체 시나리오를 **실제 변이체**로 바꿀 수 있다.

구조 파일(`cif/`, 약 9MB)은 저장소에 넣지 않는다. `fetch_cif.sh`로 다시 받는다.

## 채점할 수 있는 두 지점

### 1. 보류 대 예측 갈림길 (`score_hold_vs_predict.py`)

관문(`logic/agent_session.py` `allowed_tools`)은 공개 구조와 완전히 일치하지 않으면
`predict_structure`와 `hold_candidate`를 **함께** 연다. `hold_candidate`의 도구 설명은
"예측 입력으로 쓸 서열 자체가 없거나 너무 짧을 때만"이라고 못 박는다.

그러므로 서열이 멀쩡한 이 10건의 정답은 전부 `predict_structure`다.
**정답이 코드가 아니라 도구 설명에 적혀 있어 채점이 성립한다.**

Boltz-2는 스텁으로 막으므로 유료 예측 호출은 0회다. Nemotron만 부른다.

### 2. 예측 에피토프 F1 (`score_epitope.py`)

예측 구조의 표적쪽 접촉 잔기를 결정 구조의 것과 집합으로 비교한다.
엔트리마다 construct 시작 위치가 달라 1N8Z 표적 서열 좌표로 옮긴 뒤 비교한다.

결정 구조를 예측 자리에 넣어 채점기를 검증했다(7사례 전부 기대대로).

| 사례 | F1 | 뜻 |
|---|---|---|
| 1N8Z → 1N8Z | 1.000 | 자기 자신 |
| 6BGT(트라스투주맙 변이체) → 1N8Z | 0.923 | **천장** — 결정 구조끼리도 이만큼 어긋난다 |
| 3BE1(트라스투주맙 골격) → 1N8Z | 0.889 | 같은 에피토프 |
| 9L1S(퍼투주맙 변이체) → 1S78 | 0.840 | 같은 에피토프 |
| 9T3R → 1S78 | 0.488 | 부분 겹침 |
| 1S78 → 1N8Z / 5O4G → 1N8Z | 0.000 | 다른 자리. 부분 점수 없음 |

**읽는 법**: 0.9 근처면 다른 결정 구조만큼 맞힌 것이다(더 올릴 여지가 사실상 없다).
0.5 근처면 자리는 맞고 세부가 틀렸다. 0이면 아예 다른 자리다.

참고로 `of3-crosscheck`의 Boltz-2 실측은 HER2쪽 접촉 19개 중 5개(재현율 0.26)였다.
천장인 0.95(6BGT)와 견주면 예측 구조 품질이 현재 병목이다.

## 파일

| 파일 | 내용 |
|---|---|
| `fetch_seqs.py` | RCSB에서 10건의 entity 서열·설명을 받는다 |
| `fetch_cif.sh` | 10건의 mmCIF를 `cif/`로 받는다(git 제외) |
| `calc_contacts.py` | 12건의 표적–항체 접촉 잔기를 계산한다. 복합체가 여러 벌이면 벌 단위로 쪼갠다 |
| `epitope_overlap.py` | 접촉 잔기를 1N8Z 좌표로 옮겨 서로 겹쳐 본다 |
| `score_epitope.py` | 에피토프 F1 채점기 + 검증 7사례 |
| `probe_match.py` | 구조 조회 판정 채점(모델·네트워크 없음) |
| `gate_run.py` | 도구·관문을 실제 10건으로 끝까지 구동(모델 없음, 예측 스텁) |
| `score_hold_vs_predict.py` | 보류 대 예측 갈림길을 실제 에이전트로 채점 |
| `check_sample_agreement.py` | 같은 입력 5샘플의 에피토프가 서로 일치하는지 잰다(캐시만 사용) |
| `generated/*.json` | 위 스크립트들의 결과 |

## 돌리는 법

```bash
# 구조 파일 받기 (한 번만, git 제외)
bash docs/topics/her2/assets/goldset/fetch_cif.sh

# 모델을 부르지 않는 것들
python docs/topics/her2/assets/goldset/probe_match.py
python docs/topics/her2/assets/goldset/gate_run.py
python docs/topics/her2/assets/goldset/calc_contacts.py     # cif/ 필요
python docs/topics/her2/assets/goldset/epitope_overlap.py   # cif/ 필요
python docs/topics/her2/assets/goldset/score_epitope.py
python docs/topics/her2/assets/goldset/check_sample_agreement.py

# Nemotron을 부른다 (유료 예측은 0회)
python docs/topics/her2/assets/goldset/score_hold_vs_predict.py --sleep 300
python docs/topics/her2/assets/goldset/score_hold_vs_predict.py --summary
```

## 한도 주의

`integrate.api.nvidia.com`은 `RateLimit-*`·`Retry-After` 헤더를 **하나도 주지 않는다**
(2026-09-26 직접 확인). 남은 횟수를 알 방법이 없다.

실측에서 에이전트는 모델 호출 3~4번 만에 429를 맞았다. 갈림길 선택은 3번째 호출에서
끝나므로 그 뒤 429가 나도 이 채점에는 영향이 없다. `score_hold_vs_predict.py`는
`reached_fork`가 참인 표본만 세고, 끊긴 후보는 같은 명령을 다시 돌리면 이어서 한다.

빈 응답이 429 직전에 나오는 것을 관측했다(2026-09-26 22:20). 빈 응답이 한도의
앞 단계일 가능성이 있으나 **[확인 필요: 관측 2건뿐이라 단정할 수 없다]**.
