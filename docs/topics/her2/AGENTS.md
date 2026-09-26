# HER2 설계 작업 가이드

## 1. WHAT — 역할

HER2와 항체 후보를 비교·검토하는 현재 프로젝트의 기능·판단 흐름·검증 범위를 관리한다.

## 2. CONTENTS — 파일과 형식

- [overview.md](overview.md) — 프로젝트 목적·입력·산출물·분석 경계
- [agent-design.md](agent-design.md) — 상태에 따른 판단 분기·도구
- [validation.md](validation.md) — 전체 데모·첫 기술 검증·미정 항목
- [a01-reference-inputs.md](a01-reference-inputs.md) — A-01 공개 구조·서열·assembly·잔기 대응 조사와 D1/D2 인계, Q04/G1 검토 대기
- [a02-structure-metrics.md](a02-structure-metrics.md) — 승인 공개 구조의 접촉·표면적·정렬 계산, 누락 처리와 기하학적 겹침의 해석 한계
- [a03-glycan-context.md](a03-glycan-context.md) — 동일 단백질에서 관측 당 포함·제외 표면 비교, 당 identity·공유결합·누락 검증과 B 인계
- [a03-prediction-input-review.md](a03-prediction-input-review.md) — 예측 자료 가용성·서열 대응 검토, 중쇄 불일치·좌표 부재와 후속 계산 검증 기준
- [logic-b-handoff.md](logic-b-handoff.md) — 로직 B 실행부의 현재 동작 범위와 D3–D6 인계 초안
- [nat-agent-loop.md](nat-agent-loop.md) — 로직 B를 NAT tool-calling 루프로 바꾸는 설계, A→B 전환 기준과 로드맵. 구현·측정 완료, 기본 모드 `nat`로 전환
- [nat-agent-loop-plan.md](nat-agent-loop-plan.md) — 위 설계의 태스크별 구현 계획 (Task 1–7, 6B 조건부)

형식: Markdown 중심. 웹 서비스 기술 선택·잠정안은 [ARCHITECTURE](../../ARCHITECTURE.md)와 [ADR](../../ADR.md)을 따른다. 구현·배포는 미검증이다.

## 3. HOW — 수정 방법

주제를 묻는 질문에는 overview.md를 먼저 읽는다. 판단 흐름은 agent-design.md, 완료 확인은 validation.md를 기준으로 삼고 같은 설명을 여러 문서에 복제하지 않는다. 도구 조건은 ../../tools/her2-toolkit.md와 맞춘다.

## 4. ⛔ HOW NOT — 주의할 함정

- 구조 신뢰도와 계산 지표를 실제 항체 결합력·치료 효능으로 단정하지 않는다 — 설계와 실험적 검증의 범위가 다르다.

## 5. WHERE — 의존성과 경계

도구·API는 ../../tools/, 제출 요건은 ../../hackathon/에 의존한다.

## 6. WHY — 배경

<!-- prev: 공개 구조 분석·예측 API 한 건을 먼저 검증하는 후보로 관리하던 상태에서, 전체 데모를 구현하는 현재 프로젝트로 갱신. -->
원문은 2026-09-24 설계와 관련 주제 설명 자료다. 해커톤 제출용 전체 흐름을 구현하며, 공개 구조 분석·Boltz-2 한 건은 첫 기술 검증 단계다. HER2 서비스 구현과 분석 성능 검증은 아직 없다.

## 7. COMMANDS — 검증 명령

저장소 루트에서 `git diff --check`로 공백 오류를 확인하고 변경 문서의 상대 링크·import 대상을 직접 확인한다. 앱 빌드·테스트 명령은 아직 없다.

## 8. ⚠️ LEARNED CAUTIONS — 학습된 주의사항

@./LEARNED_CAUTIONS.md

[누적 주의사항](LEARNED_CAUTIONS.md)을 필요한 작업에서 읽는다.
