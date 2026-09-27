# 7c5cf2d 기준 에이전트 평가 결과

평가일: 2026-09-27 · commit: `7c5cf2dfcaf2e9be5f10f1da7ea57e89fd3a8f48` · branch: `docs/agent-evaluation` · 루브릭/데이터: `hackathon-v1`.

PR 준비 시 원격 main은 `013c8c40ecf48a9dfb459c729f86dd12d277a3f3`으로 진행되어 있었다. 아래 13점과 실패 항목은 **7c5cf2d의 기준 기록**이며 최신 main을 재평가한 결과가 아니다. 후속 변경은 이 기록에 섞거나 자동 병합하지 않았다.

## 결과

**오프라인 10개 사례 + 영속 화면 검토: 13/20점. 치명 실패 항목 5개로 내부 준비 목표 미달이다.** 20개 항목 모두 근거를 확인했다. 이 점수는 도구·규칙·저장 관문과 화면의 점검 결과이며 실제 모델의 정확도 점수가 아니다.

| 영역 | 점수 | 결과 |
|---|---:|---|
| 입력·대응 | 2/4 | 정상 대응·화면 연결 통과, 잘못된 표적 탐지·중단 실패 |
| 도구 선택 | 4/4 | 규칙 기준선의 오류 중단·기존 구조 사용·변이 예측 경로 통과 |
| 계산·구조 | 2/4 | 공개 접촉 재현·3D 통과, 손상 예측의 무효 처리·근거 분리 실패 |
| 근거·보류 | 1/4 | 미계산 한계는 표시, 접촉 주제의 별도 판정·과장/단위 오류 차단 실패 |
| 장애 복구 | 4/4 | timeout 표시·부분 결과 보존·중단 후 이어가기 통과 |

정상 계산과 복구가 동작한다는 점은 확인했다. 그러나 **잘못된 입력·의견을 정상 근거처럼 받아들이는 경로**가 남아 있어 총점만으로 준비 완료를 선언할 수 없다. 실제 모델이 이런 오류를 자주 낸다는 측정은 아니며, 오류가 들어왔을 때 제품 경계가 막지 못한다는 결과다.

## 실패 항목과 우선 수정 범위

| 항목 | 확인한 실제 동작 | 우선 조치 |
|---|---|---|
| I3·I4(치명) | P04626에 합성 A 607자 표적을 넣었는데 입력 통과·1N8Z/1S78 재사용·두 후보 완료 | 표적 식별자/서열/구조 구간 대응을 확인한 뒤 재사용 허용 |
| S3·S4(치명) | 좌표 없는 예측 응답과 confidence 0.99를 넣자 예측 구조에 기존 1N8Z 접촉 39개 기록 | 좌표·사슬 검증과 선택된 구조/근거의 출처·해시 일치를 확인 |
| E3·E4(치명) | “치료 효능 입증·부작용 없음”, “친화도 39 nM” 문장이 정상 저장됨 | 설명의 항목·단위·해석 범위를 검증하고 근거 밖 단정을 차단 |
| E1 | 규칙 기준선은 확인된 접촉도 `interface_review / needs_confirmation`으로 묶음 | 사용자가 결정한 주제별 판정을 규칙·모델·보고에 일관되게 적용 |

치명 실패는 I4/S3/S4/E3/E4의 **5개 채점 항목**이다. 서로 관련된 항목이 있으므로 독립 결함 5개라는 뜻은 아니다. E1은 이번에 합의한 제품 기준과 기존 구현의 차이이며 회귀로 단정하지 않는다. 제품 로직은 이번 평가에서 수정하지 않았다.

## 실제 Nemotron 정상 실행 1회

사용자 승인 범위대로 정상 입력 한 건(후보 두 개)을 실제 NAT/Nemotron 경로에서 실행했다. Boltz-2는 실행기에서 대역으로 고정했으며, 이 실행에서는 예측 시도 자체가 없었다.

| 항목 | 관측 |
|---|---|
| 모델 | `nvidia/nemotron-3-super-120b-a12b`, 저장소 NAT 설정 사용 |
| 전체 소요 | 20.117초 |
| 완료 | trastuzumab·pertuzumab 모두 completed |
| 경로 | 후보마다 check_input → lookup_public_structure → use_experimental_structure → compare_structure → submit_opinion |
| 도구 기록 | 총 10개 허용, 거부 0개; LLM HTTP 요청 수와 동일한 지표가 아님 |
| 의견 | 두 후보 모두 reviewable. 접촉 39/56과 실험 구조를 근거로 제시 |
| 규칙 복구 | 이번 실행에서는 없음 |
| 실제 Boltz-2 호출 | 0회 |

첫 후보의 모델 설명은 충돌·표면 노출이 pending이라고 명시했다. 두 번째 후보의 설명은 공개 구조와 접촉을 근거로 들었고, 결과의 limitations에는 미계산 항목이 남았다. 이는 **한 정상 실행의 관측**이며 반복 안정성·새 후보의 도구 선택·예측 품질·환각률을 입증하지 않는다.

규칙 기준선은 같은 정상 입력에 추가 확인, 이번 모델 실행은 검토 가능으로 답했다. 서버 장애로 규칙 경로가 선택될 때도 주제별로 일관된 의미를 유지하도록 다듬을 필요가 있다. 이 실제 모델 결과를 오프라인 실패 항목의 점수 대신 넣지 않았다.

실호출 근거: [manifest](assets/hackathon-evaluation/runs/2026-09-27-live/manifest.json), [요청](assets/hackathon-evaluation/runs/2026-09-27-live/C01/request.json), [결과·도구 경로·의견](assets/hackathon-evaluation/runs/2026-09-27-live/C01/observation.json), [SDK 출력](assets/hackathon-evaluation/runs/2026-09-27-live/sdk-output.txt). SDK 출력은 인증정보 포함 여부를 확인해 보존했다. 토큰 사용량·비용·LLM 요청 횟수는 수집하지 못했으므로 임의 수치를 적지 않았다.

## 화면·저장 경로

별도 폐기용 PostgreSQL 17, 영속 API, live-mode worker를 띄웠다. worker의 모델 키는 제거하고 규칙 모드로 정상 공개 입력을 처리했다. 기존 API·worker·프런트 코드와 동일 출처 프록시를 사용했고 운영 DB는 사용하지 않았다.

브라우저 버튼으로 접수한 실행은 `run-90be4f57bb5f4bd5ae63ab1145c6d84d`다. 두 후보를 전환해 실험 구조·39/56 접촉 강조·계산 정의·출처·보고서·결과 파일 연결을 확인했다. 화면의 “실제 실행” 표시는 제품의 `data_mode=live` 의미이며 이번 화면 검사에서 모델 API를 호출했다는 뜻은 아니다.

[저장 입력](assets/hackathon-evaluation/runs/2026-09-27-offline/ui/persisted-input.json)은 출처 표식 `example_id`를 제외하면 동결된 reference 입력과 정확히 같음을 대조했다. 확인 후 평가용 브라우저·API·worker·개발 서버와 임시 DB 컨테이너를 종료했고 결과 파일은 남겼다.

- [영속 결과 JSON](assets/hackathon-evaluation/runs/2026-09-27-offline/ui/persisted-result.json)에는 실행/결과만 보존했고 세션 cookie·인증 토큰은 내보내지 않았다.
- [Trastuzumab 화면](assets/hackathon-evaluation/runs/2026-09-27-offline/ui/persisted-trastuzumab.png), [Pertuzumab 화면](assets/hackathon-evaluation/runs/2026-09-27-offline/ui/persisted-pertuzumab.png), [보고서 텍스트](assets/hackathon-evaluation/runs/2026-09-27-offline/ui/persisted-report-ax.txt)를 확인 근거로 남겼다.
- 초기의 별도 동기 `service.app` 경로에서는 실험 구조 다운로드가 실패했다. [오류 화면](assets/hackathon-evaluation/runs/2026-09-27-offline/ui/sync-path-error.png)과 [텍스트](assets/hackathon-evaluation/runs/2026-09-27-offline/ui/sync-path-ax.txt)를 별도 기록했다. 이 보조 경로의 오류를 영속 서비스 실패로 집계하지 않았다. 동기 경로로 시연한다면 별도 수정이 필요하다.

공개 배포·브라우저 전체 회귀·세션 만료/보안·부하 검사는 이번 점수의 범위가 아니다. 정상 저장 경로를 실제로 확인한 것이며 서비스 테스트 전체를 DB와 함께 재실행한 것은 아니다.

## 재현과 기록

- [채점표](assets/hackathon-evaluation/runs/2026-09-27-offline/scorecard.json): 20개 항목별 통과/실패·증거 위치·검토 메모.
- [집계](assets/hackathon-evaluation/runs/2026-09-27-offline/score.json): 13/20, 치명 5개, 미실행 0개.
- [오프라인 실행 manifest](assets/hackathon-evaluation/runs/2026-09-27-offline/manifest.json): 기준 commit·관련 코드 해시·데이터 잠금 해시. 같은 폴더의 C01–C10에 입력·진행·출력을 보존했다.
- [$agent-evaluate](../../../.agents/skills/agent-evaluate/SKILL.md): 고정 데이터 검사 → 새 폴더에 실행 → 화면/근거 검토 → 채점·보고의 반복 절차.

오프라인 원시 자료의 일부 `decided_by=model`은 테스트가 `CandidateTools`를 직접 호출해서 생성한 기존 코드 표기다. `offline-no-model`과 manifest의 실행 모드를 함께 읽어야 하며 실모델 호출로 세지 않는다. 각 `run.status` 역시 평가 통과 여부가 아니다.

독립 접촉 검산·파일 무결성·입력 규격·모든 채점 증거의 상대 경로/JSON pointer 확인을 수행했다. 채점기 테스트 9개와 스킬 형식 검사를 통과했다. 기존 회귀검사 147 passed/22 skipped/1 deselected 결과는 앞선 리뷰 실행이며, 이번 모델 성공률로 합치지 않는다.

다른 세션의 미커밋 변경은 포함하지 않았다. 이후 수정이 main에 반영되면 새 코드 버전으로 동일 데이터를 재실행하고, 이전 점수를 새 에이전트의 현재 점수라고 사용하지 않는다.
