# NVIDIA Hackathon — 공통 에이전트 작업 지침

이 파일은 작업 영역 지도다. 해당 영역의 AGENTS.md를 먼저 읽고 필요한 문서만 연다.
현재는 팀 저장소 초기화 단계이며 최종 주제·기술 스택은 미확정이다. HER2 항체 검토 설계만 주제 후보로 보존했다.

## 영역별 가이드

- [docs/AGENTS.md](docs/AGENTS.md) — 문서 전체 구조와 출처 관리.
- [docs/hackathon/AGENTS.md](docs/hackathon/AGENTS.md) — 규정·신청·교육·데모 준비.
- [docs/topics/AGENTS.md](docs/topics/AGENTS.md) → [HER2 가이드](docs/topics/her2/AGENTS.md) — 보존된 주제 설계.
- [docs/tools/AGENTS.md](docs/tools/AGENTS.md) — NVIDIA 스킬·모델·도구와 환경 조건.
- [docs/references/AGENTS.md](docs/references/AGENTS.md) — 출처와 문서 선별 근거.
- [docs/collaboration/AGENTS.md](docs/collaboration/AGENTS.md) — `.agents/`, `.codex/`, `.claude/`, `.github/`와 팀 협업.

## 공통 작업 원칙

- 요청 범위와 완료 기준을 확인하고 필요한 변경만 한다. 기존 팀원 변경을 보존한다.
- 구현 전에 기능 목적을 명확히 하고, 미확정 주제·도구·성능을 확정 사실로 기록하지 않는다.
- 작업에 맞는 검증을 수행하고 실제 실행 결과와 미검증 한계를 구분해 보고한다.
- [CONTRIBUTING.md](CONTRIBUTING.md)의 커밋·PR 규칙을 따른다. 사용자 요청 없이 커밋·push·병합하지 않는다.
- 최상위 README.md는 사용자 요청으로 비어 있다. 별도 요청 전 내용을 채우지 않는다.
- AGENTS.md가 지침 원본이다. CLAUDE.md는 같은 폴더의 `@AGENTS.md` 참조만 유지한다.

## 공통 스킬과 학습

원본은 `.agents/skills/`. Claude 진입 파일은 `.claude/skills/`에서 공통 원본을 읽는다.
명시 호출된 `$learn` 또는 `/learn`은 대상 영역의 LEARNED_CAUTIONS.md에만 기록한다.
공통 스킬은 명시 호출로 사용한다. 설치·검토 요청은 해당 스킬의 실행 승인이 아니다.
