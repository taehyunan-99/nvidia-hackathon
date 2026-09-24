# 해커톤 진행 작업 가이드

## 1. WHAT — 역할

참가 규정, 신청 필드, 교육 내용과 데모 준비 수준을 정리한다.

## 2. CONTENTS — 파일과 형식

- `requirements.md` — 당시 공식 요구사항·미확인 사항
- `application-form.md` — 공개 폼 스냅샷
- `nemoclaw-course-notes.md` — 교육 노트
- `demo-readiness.md` — 내부 데모 준비 제안

형식: Markdown 중심. 애플리케이션 기술 스택은 미확정.

## 3. HOW — 수정 방법

규정 수정 시 주최 출처와 확인일을 기록한다. 실제 제출 직전 폼·일정·허용 조건을 재확인한다.

## 4. ⛔ HOW NOT — 주의할 함정

- 데모 준비 제안을 공식 배점이나 필수 조건으로 바꾸지 않는다 — 준비용 분석과 규정은 근거가 다르다.

## 5. WHERE — 의존성과 경계

주제·도구 선택이 이 문서의 규정에 의존한다. 공식 여부의 근거는 references에서 추적한다.

## 6. WHY — 배경

신청 폼 기록은 당시 공개 화면의 분석이며 신청 완료·교육 수료 증거가 아니다.

## 7. COMMANDS — 검증 명령

저장소 루트에서 `git diff --check`로 공백 오류를 확인하고 변경 문서의 상대 링크·import 대상을 직접 확인한다. 앱 빌드·테스트 명령은 아직 없다.

## 8. ⚠️ LEARNED CAUTIONS — 학습된 주의사항

@./LEARNED_CAUTIONS.md

[누적 주의사항](LEARNED_CAUTIONS.md)을 필요한 작업에서 읽는다.
