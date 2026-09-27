# 주제 작업 가이드

## 1. WHAT — 역할

현재 진행하는 Bio-3(HER2 항체 후보 검토 에이전트)의 기능과 설계를 관리한다.

## 2. CONTENTS — 파일과 형식

- [her2/overview.md](her2/overview.md) — 프로젝트 개요
- [her2/agent-design.md](her2/agent-design.md) — 판단 흐름
- [her2/validation.md](her2/validation.md) — 구현·검증 범위

형식: Markdown 중심. 웹 서비스 기술 선택·잠정안은 [ARCHITECTURE](../ARCHITECTURE.md)와 [ADR](../ADR.md)을 따른다. 로컬 서비스·분석 구현이 있으며 공개 배포는 미검증이다. 현재 상태는 [서비스 가이드](../frontend-hosting/AGENTS.md)와 코드에서 확인한다.

## 3. HOW — 수정 방법

주제 질문에는 her2/overview.md를 먼저 읽는다. 구현 작업은 her2/AGENTS.md를 읽고 목적·설계·검증 문서를 필요한 순서로 확인한다.

## 4. ⛔ HOW NOT — 주의할 함정

<!-- prev: 주제 미정이므로 선정 완료로 표시하지 않던 규칙을 현재 진행 주제에 맞게 갱신. -->
- HER2를 탐색 중인 주제 후보로 되돌려 설명하지 않는다 — 현재 진행 주제다. 세부 구현 미정 사항과 주제 선정 여부를 구분한다.

## 5. WHERE — 의존성과 경계

hackathon의 규정, tools의 실행 조건과 references의 출처를 함께 확인한다.

## 6. WHY — 배경

24번 HER2 설계를 바탕으로 프로젝트를 진행한다. 해커톤 시연은 입력부터 3D 비교·결과 보고까지 포함한다.

## 7. COMMANDS — 검증 명령

저장소 루트에서 `git diff --check`로 공백 오류를 확인하고 변경 문서의 상대 링크·import 대상을 직접 확인한다. 제품 검사는 서비스 가이드의 격리 DB·빌드 명령을 따른다.

## 8. ⚠️ LEARNED CAUTIONS — 학습된 주의사항

@./LEARNED_CAUTIONS.md

[누적 주의사항](LEARNED_CAUTIONS.md)을 필요한 작업에서 읽는다.
