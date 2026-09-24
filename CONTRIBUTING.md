# 팀 협업 규칙

## 작업과 브랜치

- 현재는 `main`에서 직접 작업한다. 별도 브랜치·worktree는 요청한 작업에만 만든다. 작업 목적은 이슈 또는 대화의 간단한 설명으로 공유한다.
- 브랜치 이름은 `<type>/<short-description>`; `feat`, `fix`, `docs`, `chore` 등을 사용한다.
- 같은 파일을 동시에 수정할 때 담당 범위를 먼저 공유한다. 다른 사람의 미커밋 변경을 덮어쓰지 않는다.

## 커밋

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) 형식인 `<type>(<scope>): <summary>`를 사용한다. scope는 선택이다.
유형은 `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `build`, `ci`, `perf`, `revert`를 사용한다.
설명은 한국어 또는 영어로 쓰되 한 커밋은 하나의 목적을 담는다.
예: `docs(hackathon): 신청서 제출 조건 정리`.

## PR과 병합 — 작업 브랜치를 사용하는 경우

- PR 제목도 커밋 형식을 따르며, 목적·변경점·검증 결과·남은 한계를 PR 템플릿에 적는다.
- 미완료 작업은 Draft PR로 공유한다. 작성자 외 팀원 1명 이상 검토 후 squash merge를 기본으로 한다.
- 관련 검증을 통과한 뒤 병합한다. 코드가 생기면 실제 스택에 맞는 검사 명령을 추가한다.
- 현재 main 직접 작업에서는 요청한 커밋·일반 push를 수행한다. 공유 브랜치 force push와 보호 규칙 우회는 하지 않는다. PR을 사용하는 작업의 충돌은 해당 작업 브랜치에서 해결한다.
- 위 규칙은 팀 운영 기준이다. GitHub 보호 규칙·필수 승인·자동 검사는 별도 설정 전까지 강제되지 않는다.

## 문서와 에이전트

루트 [AGENTS.md](AGENTS.md)에서 작업 영역을 찾고 하위 가이드를 읽는다.
문서 수정은 [문서 가이드](docs/AGENTS.md), 에이전트·공통 스킬 설정은 [설정 안내](docs/collaboration/agent-setup.md)를 따른다.
비밀키는 로컬 환경변수나 추후 CI secret으로 전달한다. 예제 파일에는 실제 값을 넣지 않는다.
AI는 실행하지 않은 검사를 성공으로 기록하거나 사용자 요청 없이 커밋·push·병합하지 않는다.
