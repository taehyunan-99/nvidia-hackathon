# 팀 협업 작업 가이드

## 1. WHAT — 역할

팀원과 Codex·Claude Code가 같은 지침·스킬·PR 절차를 사용하도록 한다.

## 2. CONTENTS — 파일과 형식

- `agent-setup.md` — 공통 원본·Claude 진입 파일·개인 설정
- `../../CONTRIBUTING.md` — 브랜치·커밋·PR 규칙
- `../../.github/pull_request_template.md` — PR 검토 양식

형식: Markdown 중심. 현재 애플리케이션 스택은 React·TypeScript·FastAPI·PostgreSQL이며 실행 안내는 서비스 가이드를 따른다.

## 3. HOW — 수정 방법

설정 변경 전 영향받는 클라이언트를 확인한다. 스킬 원본은 .agents/skills에 두고 Claude 진입 파일도 연결한다. task-workflow의 실행을 위한 명시 호출은 작업 브랜치 생성·전환을 허용한다. 새 작업은 검증한 main에서 분기하고 같은 작업은 미병합 브랜치를 재개한다. 설치·검토·수정 요청은 실행 승인이 아니며 별도 worktree는 지정·승인된 경로에만 만든다.

## 4. ⛔ HOW NOT — 주의할 함정

- CLAUDE.md에 원본 지침을 복제하거나 learn 기록을 추가하지 않는다 — AGENTS.md와 서로 달라지는 것을 막기 위함이다.

## 5. WHERE — 의존성과 경계

루트 및 하위 AGENTS.md, .agents/, .codex/, .claude/, .github/의 설정 작업을 함께 안내한다.

## 6. WHY — 배경

Windows 팀원이 있어 심볼릭 링크 없이 일반 파일·상대 경로를 사용한다. 모델·개인 권한·기술 스택은 강제하지 않는다.
팀은 서비스 1명과 로직·워크플로우 2명으로 일하며, 세부 담당과 연결 규격은 진행하면서 합의한다. [현재 분담](../topics/her2/overview.md#팀-작업-분담)을 참고한다.

## 7. COMMANDS — 검증 명령

저장소 루트에서 `git diff --check`와 상대 링크·import 대상을 확인한다. handoff 실행 도구를 바꿀 때는 Python 3.11+ 환경에서 `python3 -m unittest discover -s .agents/skills/handoff/tests -p 'test_*.py'`와 `node --test .agents/skills/handoff/tests/parallel-wait.test.cjs`를 실행한다. 이는 공통 스킬 검사이며 Bio-3 제품 검사는 [서비스 가이드](../frontend-hosting/AGENTS.md)를 따른다.

## 8. ⚠️ LEARNED CAUTIONS — 학습된 주의사항

@./LEARNED_CAUTIONS.md

[누적 주의사항](LEARNED_CAUTIONS.md)을 필요한 작업에서 읽는다.
