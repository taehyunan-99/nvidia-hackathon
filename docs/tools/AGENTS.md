# 도구와 스킬 작업 가이드

## 1. WHAT — 역할

에이전트 구성요소의 역할과 HER2 설계에 필요한 실행 조건을 설명한다.

## 2. CONTENTS — 파일과 형식

- `stack-overview.md` — 스킬·모델·도구 관계
- `nvidia-skills-guide.md` — 스킬 선택과 설치 전 확인
- `agent-frameworks.md` — NAT·NemoClaw·OpenShell
- `models-and-nim.md` — 모델·NIM·API
- `tools-and-mcp.md` — 도구 연결·평가
- `runtime-and-costs.md` — Windows·GPU·비용
- `her2-toolkit.md` — HER2 관련 도구만 선별

형식: Markdown 중심. 애플리케이션 기술 스택은 미확정.

## 3. HOW — 수정 방법

제품 설명, 개발용 스킬, 실제 실행 함수를 구분한다. 버전·입력·출력·환경·실행 여부를 기록하고 실제 설치는 요청 범위에서만 수행한다.

## 4. ⛔ HOW NOT — 주의할 함정

- 스킬 설치나 문서상 지원을 API 접근·데모 성공으로 기록하지 않는다 — 계정·입력별 실행 증거가 별도로 필요하다.

## 5. WHERE — 의존성과 경계

../topics/her2/overview.md가 기능 목적, agent-design.md가 도구의 실행 역할, validation.md가 완료 확인의 기준이며 ../hackathon/requirements.md가 공식 요구사항의 기준이다.

## 6. WHY — 배경

기술 카탈로그 전체보다 현재 작업에 필요한 도구를 찾을 수 있게 구성했다. 다른 도구의 실제 운영 경험은 아직 없다.

## 7. COMMANDS — 검증 명령

저장소 루트에서 `git diff --check`로 공백 오류를 확인하고 변경 문서의 상대 링크·import 대상을 직접 확인한다. 앱 빌드·테스트 명령은 아직 없다.

## 8. ⚠️ LEARNED CAUTIONS — 학습된 주의사항

@./LEARNED_CAUTIONS.md

[누적 주의사항](LEARNED_CAUTIONS.md)을 필요한 작업에서 읽는다.
