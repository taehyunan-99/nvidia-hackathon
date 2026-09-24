# 문서 전체 작업 가이드

## 1. WHAT — 역할

해커톤 운영, 보존된 HER2 주제 후보, 도구와 협업 규칙을 찾는 문서 지도.

## 2. CONTENTS — 파일과 형식

- `hackathon/` — 규정·신청·교육·데모
- `topics/her2/` — HER2 후보 설계
- `tools/` — 실행 도구·스킬·환경
- `references/` — 출처·선별 기록
- `collaboration/` — 팀 공통 설정
- `README.md` — 문서 목차

형식: Markdown 중심. 애플리케이션 기술 스택은 미확정.

## 3. HOW — 수정 방법

작업할 하위 영역의 AGENTS.md를 먼저 읽는다. 새 문서는 해당 폴더에 넣고 docs/README.md를 갱신한다. 파일명은 번호 없는 영문 kebab-case를 쓴다.

## 4. ⛔ HOW NOT — 주의할 함정

- 조사 기준일과 미검증 표시를 제거하지 않는다 — 현재 검증된 사실로 오인될 수 있다.

## 5. WHERE — 의존성과 경계

루트 AGENTS.md에서 진입하며 각 영역 가이드와 출처 기록으로 연결된다.

## 6. WHY — 배경

기존 개인 조사에서 팀 진행에 필요한 자료만 선별했다. 다른 주제 후보를 다시 자동으로 가져오지 않는다.

## 7. COMMANDS — 검증 명령

저장소 루트에서 `git diff --check`로 공백 오류를 확인하고 변경 문서의 상대 링크·import 대상을 직접 확인한다. 앱 빌드·테스트 명령은 아직 없다.

## 8. ⚠️ LEARNED CAUTIONS — 학습된 주의사항

@./LEARNED_CAUTIONS.md

[누적 주의사항](LEARNED_CAUTIONS.md)을 필요한 작업에서 읽는다.
