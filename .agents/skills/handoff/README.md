# Handoff

사용자 제공 원본 전체를 복사한 뒤 이 저장소에서만 수정한 버전이다.

- `$handoff init|next|done|pause|start|inspect` — 검증된 상태·다음 작업·근거 인수인계.
- 순차 인수인계는 Codex와 Claude에서 공통 SKILL.md를 읽는다.
- 병렬 운영은 명시 요청한 별도 Codex 앱 작업과 실제 작업 ID가 필요하다.
- Python 3.11+, Git. 병렬 worktree 등록·프로세스 관리 도구는 스킬 내부에 포함한다.
- [전체 절차](SKILL.md), [실행 환경·검증 한계](references/runtime-portability.md).

공통 원본은 `.agents/skills/handoff/`이며 개인 경로·회사 checkout·심볼릭 링크는 필요 없다.
