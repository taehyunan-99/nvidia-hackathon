# 주제 작업 가이드

## 1. WHAT — 역할

보존하기로 한 주제 후보의 설계를 관리한다.

## 2. CONTENTS — 파일과 형식

- `her2/` — HER2 항체 후보 검토 설계

형식: Markdown 중심. 애플리케이션 기술 스택은 미확정.

## 3. HOW — 수정 방법

HER2 작업은 her2/AGENTS.md를 읽는다. 최종 선택 시 결정 이유·범위·미해결 조건을 명시한다.

## 4. ⛔ HOW NOT — 주의할 함정

- 현재 폴더의 유일한 후보라는 이유로 선정 완료로 표시하지 않는다 — 최종 주제는 미확정이다.

## 5. WHERE — 의존성과 경계

hackathon의 규정, tools의 실행 조건과 references의 출처를 함께 확인한다.

## 6. WHY — 배경

사용자 요청으로 24번 HER2 설계 관련 내용만 남기고 다른 아이디어 문서는 제외했다.

## 7. COMMANDS — 검증 명령

저장소 루트에서 `git diff --check`로 공백 오류를 확인하고 변경 문서의 상대 링크·import 대상을 직접 확인한다. 앱 빌드·테스트 명령은 아직 없다.

## 8. ⚠️ LEARNED CAUTIONS — 학습된 주의사항

@./LEARNED_CAUTIONS.md

[누적 주의사항](LEARNED_CAUTIONS.md)을 필요한 작업에서 읽는다.
