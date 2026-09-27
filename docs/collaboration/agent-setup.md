# Codex·Claude Code 공통 설정

설정 확인일: 2026-09-24. Windows와 macOS에서 공유할 수 있도록 일반 파일과 상대 경로로 구성한다.

## 작업 지침

각 영역의 `AGENTS.md`가 원본이다. 같은 폴더의 `CLAUDE.md`는 `@AGENTS.md` 한 줄로 가져온다.
`agentic-project-init`의 root map·8섹션 가이드·분리된 주의사항 구조를 적용했다.
GitHub 최신 both 모드도 AGENTS.md 원본과 CLAUDE.md import 방식을 사용하며 sync hook은 필요 없다.
가이드는 AGENTS.md만 수정한다. 영역별 가이드의 배경은 확인된 요구와 조사 기록에 한정했다.

## 공통 스킬

- 원본: `.agents/skills/<skill-name>/SKILL.md`와 필요한 참조 파일.
- Codex: 저장소의 `.agents/skills/`에서 탐색한다. `.codex/skills/` 복사본은 만들지 않는다.
- Claude: `.claude/skills/<skill-name>/SKILL.md`에 이름·설명과 공통 원본을 읽으라는 지침을 둔다.
- Windows의 심볼릭 링크 권한에 의존하지 않는다. Claude의 wrapper는 공통 원본을 명시적으로 읽어야 한다.
- 새 스킬은 사용자 요청 시 공통 원본과 Claude 진입 파일을 함께 추가하고, 출처·버전·라이선스·참조 의존성을 확인한다.

`learn`은 Codex에서 `$learn`, Claude에서 `/learn`으로 명시 호출한다.
원본의 메모·대상·근거 확인 절차를 거친 후 해당 영역 LEARNED_CAUTIONS.md에 누적한다. 본문 가이드의 8번 섹션에서 이 파일을 참조한다.

`agent-evaluate`는 [공통 원본](../../.agents/skills/agent-evaluate/SKILL.md)을 명시 호출해 HER2 에이전트를 평가하고 점수·실행 근거를 기록한다. 프로젝트 자체 작성 스킬이며 평가 기준·데이터·Python 의존성은 [해커톤 평가 문서](../topics/her2/hackathon-evaluation.md)와 `uv.lock`을 따른다. 외부 스킬을 복제하거나 별도 라이선스를 부여한 것은 아니다. 기본은 오프라인이며 실제 모델 호출은 요청된 범위에서만 수행한다.

`handoff` 스킬과 검증 코드는 공유하지만 `docs/HANDOFF.md`, `docs/HANDOFF.html`, `docs/HANDOFF.md.parallel.lock`, `docs/handoff-runs/`는 `.gitignore`로 제외한 개인 기록이다. 각자 별도 clone에서 현재 인계 파일 하나를 관리하고, 다음 세션도 같은 checkout에서 이어간다. 이 기록은 커밋·PR에 포함하지 않으며 다른 PC·clone·worktree에 자동 전달되지 않는다. 팀 진행 상황과 결정은 별도 공용 문서로 관리한다.

## Git 작업 준비

`$task-workflow` 또는 `/task-workflow` 실행은 원격 main을 확인하고 해당 작업 브랜치를 생성·전환하거나 같은 작업의 미병합 브랜치를 재개한다. 호출 자체가 브랜치 준비를 허용하며 별도 생성 승인을 반복 요청하지 않는다. main 직접 작업은 사용자 명시 예외이고, 별도 worktree는 필요할 때 지정·승인된 경로에 만든다. 커밋·push·PR·정리는 각각 요청한 범위에서만 수행한다.

## 개인별 설정과 최초 확인

`.codex/config.toml`은 공통 설정 자리이며 현재 모델·권한 강제값은 없다. `.claude/settings.json`도 빈 설정이다.
개인 Codex 기본값은 사용자 설정에서, Claude 개인 설정은 Git에서 제외한 `.claude/settings.local.json`에서 관리한다.
Codex의 프로젝트 설정은 프로젝트 신뢰 여부에 영향을 받으므로 각자의 환경에서 확인한다.
새 checkout에서 Codex는 스킬 목록에 learn이 나타나는지, Claude는 `/memory`로 지침 로딩과 `/learn`의 공통 원본 경로를 확인한다.
이 저장소에서 두 클라이언트의 실제 세션 실행까지 검증한 것은 아니다.

## 공식 참고

- [Codex 스킬 경로](https://learn.chatgpt.com/docs/build-skills)
- [Codex 프로젝트 설정](https://learn.chatgpt.com/docs/config-file/config-basic)
- [Claude 문서 import](https://code.claude.com/docs/en/memory)
- [Claude 스킬 경로·명시 호출](https://code.claude.com/docs/en/skills)
