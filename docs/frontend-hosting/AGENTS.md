# 프런트엔드·호스팅 조사 가이드

## 1. WHAT — 역할

HER2 분석 로직을 서비스 화면·연동·운영 관점에서 읽고, 구현에 필요한 자료와 미결정 사항을 정리한다.

## 2. CONTENTS — 파일과 형식

- [bio-agent-experience.md](bio-agent-experience.md) — 분석·소개·팀 탭과 바이오 에이전트 표현 기준
- [researcher-ux-research.md](researcher-ux-research.md) — 전문가 UX 근거·화면 가설·인터뷰·평가안
- [nvidia-design-research.md](nvidia-design-research.md) — NVIDIA 공식 디자인 출처·적용 근거·범위
- [design-guide.md](design-guide.md) — 사용자 확인 시각 방향과 토큰·표현 기준
- [screen-plan.md](screen-plan.md) — 네 화면·상태·임시 구현 범위
- [overview.md](overview.md) — 조사 범위·확인 상태·사용자 인터뷰·후속 작업
- [agent-logic.md](agent-logic.md) — 분석 분기·산출물·공개 구조에서 확인한 연결 주의점
- [frontend-contract.md](frontend-contract.md) — 화면이 소비할 데이터·상태·3D 연결·계약 검토 항목
- [hosting-requirements.md](hosting-requirements.md) — 실행·저장·외부 호출·배포 조건과 실측 인계
- [temporary-contract.md](temporary-contract.md) — 사용자 요청으로 먼저 정한 v0.1.0 서비스 개발용 임시 규격
- [contracts/service.schema.json](contracts/service.schema.json) — 임시 입력·출력의 JSON Schema 원본
- [fixtures/scenarios.json](fixtures/scenarios.json) — 합성 입력·9개 모의 상태 예시
- [contracts/validate-contract.py](contracts/validate-contract.py) — 스키마·참조·상태 및 잘못된 데이터 검사

형식은 Markdown이며 조사 기준일·출처·확인 수준을 유지한다.

## 3. HOW — 수정 방법

[PRD](../PRD.md), [ARCHITECTURE](../ARCHITECTURE.md), [HER2 설계](../topics/her2/agent-design.md)를 기준으로 서비스에 필요한 내용을 연결한다. 사용자 답변은 overview.md에 기록하고 관련 상위 문서의 미결정 상태도 맞춘다.

## 4. HOW NOT — 주의할 함정

- 소비할 데이터 목록을 확정 API·구현된 응답으로 기록하지 않는다.
- 공개 자료 조회와 실제 계산·모델 호출·3D 실행 검증을 구분한다.
- 모의 응답에 실제 분석처럼 보이는 수치·사슬 대응·후보 판정을 만들지 않는다.

## 5. WHERE — 의존성과 경계

기능·과학적 범위의 원본은 ../topics/her2/, 기술 선택의 원본은 ../ARCHITECTURE.md·../ADR.md다. 이 폴더는 서비스 소비 요구와 조사 근거를 관리하며 분석 기준을 독자적으로 확정하지 않는다.

## 6. WHY — 배경

로직 구현 전에 화면과 호스팅 작업을 시작할 수 있도록, 확정 범위와 공동 검토가 필요한 연결점을 구분한다.

## 7. COMMANDS — 검증

`git diff --check`와 변경 문서의 상대 링크·참조 대상 확인. 실행하지 않은 제품 검증은 통과로 기록하지 않는다.

임시 규격 검증: 저장소 루트에서 `uv run --no-project --with jsonschema python docs/frontend-hosting/contracts/validate-contract.py`. 과학적 분석·서비스 런타임·live API 검증을 대신하지 않는다.
