---
name: task-workflow
description: 사용자가 $task-workflow 또는 /task-workflow를 명시 호출하면 원격 main과 작업 상태를 확인하고 새 작업 브랜치를 생성하거나 같은 작업의 미병합 브랜치를 재개한다. 회사·운영체제 전용 도구 없이 Git과 GitHub CLI/API를 사용한다.
---

# Task Workflow

[CONTRIBUTING.md](../../../CONTRIBUTING.md)와 적용되는 AGENTS.md를 읽는다.
이 스킬의 목적은 **구현 전에 작업 브랜치를 확보하는 것**이다. 실행을 위한 명시 호출은 해당 작업 브랜치의 생성·전환을 허용한다. 브랜치를 따로 만들어 달라는 재확인을 요구하지 않는다. 설치·검토·수정 요청은 스킬 실행 요청이 아니다.
회사 프로젝트 ID, develop, Windows SID, 고정 worktree 등록부나 외부 PowerShell 스크립트를 요구하지 않는다. 기본 base는 `main`이며 현재 운영체제의 Git과 GitHub CLI/API를 사용한다.

## 작업과 저장소 확인

1. Git 루트, origin URL, 현재 branch·HEAD, `git status --short`, staged diff, `git worktree list --porcelain`을 확인한다. 다른 checkout의 변경을 가져오지 않는다.
2. 대화에서 작업 목적을 확정하고 새 작업인지 같은 작업의 재개인지 구분한다. 이름이 없으면 목적에 맞는 `<type>/<short-description>`을 정해 보고하고 진행한다. 목적 자체가 없거나 서로 다른 작업이 섞여 있으면 필요한 내용만 질문한다.
3. origin이 있으면 `git fetch origin --prune`을 성공한 뒤 `origin/main`의 전체 SHA를 고정하고 로컬 main과 ahead/behind를 확인한다. fetch 실패나 원격 main 부재를 변경 없음으로 처리하지 않는다. 원격이 없으면 로컬 main을 기준으로 사용할 수 있으나 원격 검증이 없음을 보고한다. 사용할 base 커밋 자체가 없으면 초기 저장소 준비가 필요하다고 보고하고 중단한다.
4. 수정·staged·untracked·ignored 파일과 사용 중인 작업을 확인한다. 기존 변경은 소유 작업과 범위를 식별해 보존한다. 자동 stash·reset·clean·강제 checkout을 하지 않는다.

## 기존 작업 브랜치 재개

- 새 세션이라는 이유만으로 새 브랜치를 만들지 않는다. 현재 작업과 같은 브랜치이면 정확한 저장소·head에 대한 PR 상태를 조회한다.
- OPEN/DRAFT, PR 없음 또는 CLOSED 미병합이면 같은 작업임을 확인하고 재개한다. 같은 작업의 미커밋 변경도 보존한다. PR 조회 실패를 PR 없음이나 미병합으로 간주하지 않는다.
- MERGED PR의 브랜치는 재사용하지 않는다. 병합 후 추가 커밋이 있으면 보존하고 복구 범위를 확인한다. 정리는 정확한 PR을 지정한 [after-pr](../after-pr/SKILL.md)의 별도 호출로 처리한다.
- 다른 작업의 활성 브랜치는 전환하지 않는다. 그 작업을 재개할지, 별도 worktree에서 새 작업을 시작할지 확인한다. 다른 worktree가 사용하는 브랜치를 강제로 checkout하지 않는다.

## 작업 브랜치 생성과 전환

기본은 현재 checkout의 작업 브랜치다. 독립 작업이 동시에 필요할 때만 사용자가 지정·승인한 경로에 linked worktree를 만든다. 고정 worktree와 주 checkout을 삭제하지 않는다.

1. 새 작업의 시작점은 고정한 원격 main SHA다. 현재 checkout이 clean한 main이고 로컬 main이 그 SHA의 조상이면, 명시 호출에 포함된 준비 작업으로 branch·HEAD·clean 상태를 다시 확인한 뒤 `git merge --ff-only <verified-base-sha>`로 최신화한다. main이 앞서거나 갈라졌으면 reset·rebase하지 않고 보존한다. 무관한 로컬 커밋을 새 작업에 섞지 않는다.
2. **기존 main 작업을 작업 브랜치로 전환**하는 경우에는 로컬 HEAD를 고정하고 base와의 커밋 목록·전체 diff를 검토한다. base가 HEAD의 조상이고 앞선 변경 전부가 해당 작업이면 그 **로컬 HEAD**에서 만든다. 이 전환도 해당 작업에 대한 스킬 명시 호출에 포함된다. 다른 작업이 섞였거나 이력이 갈라졌으면 시작점을 임의 선택하지 않는다.
3. 같은 작업의 미커밋 변경이 있고 현재 HEAD가 선택한 시작 SHA와 같으면 변경을 그대로 둔 채 브랜치를 만들 수 있다. 생성 전후 staged·unstaged diff와 untracked·ignored 파일이 보존되는지 확인한다. 시작 SHA가 다르거나 변경 소유권이 불명확하면 자동으로 옮기지 않고 분리 방법을 확인한다.
4. 생성 직전에 branch·HEAD·작업 상태와 대상 이름의 로컬·원격 ref 부재를 다시 확인한다. 기존 이름이 있으면 덮어쓰지 말고 해당 브랜치의 작업·PR 상태를 확인한다. `git switch --no-overwrite-ignore -c <task-branch> <verified-start-sha>`로 생성·전환한다. 승인된 linked worktree이면 `git worktree add -b <task-branch> <path> <verified-start-sha>`를 사용한다.
5. 경로·공통 Git 디렉터리·branch·HEAD·base 대비 diff와 기존 파일 보존을 확인한다. **작업 브랜치에 있는 것이 확인된 뒤 구현을 시작한다.** main 직접 작업은 사용자가 그 작업에 대해 명시한 예외에만 허용한다.

기존 main 커밋을 전환해도 로컬 main ref는 되돌리지 않는다. 이후 squash/rebase 병합으로 main이 갈라지면 after-pr에서 별도 정리 판단이 필요할 수 있다.

## 커밋·PR·정리 경계

- 이 호출만으로 커밋·push·PR·병합·브랜치 삭제를 하지 않는다. 함께 요청된 후속 작업은 [commit](../commit/SKILL.md), [pull-request](../pull-request/SKILL.md), [after-pr](../after-pr/SKILL.md)의 절차를 따른다. 이미 승인된 브랜치 준비를 후속 단계에서 다시 승인받지 않는다.
- base가 앞섰다는 이유만으로 작업 브랜치를 자동 merge·rebase하지 않는다. PR 준비에서 관련 변경·충돌과 통합 방법을 검토한다. force push·hook 우회를 하지 않는다.
- 실패한 명령의 경로·종료 코드·상태를 확인하고, 동일한 변경 작업을 맹목적으로 반복하지 않는다.
- 새 Codex 앱 세션은 만들지 않는다. 명시 요청된 별도 세션의 병렬 작업은 [handoff](../handoff/SKILL.md)가 담당한다.

## 완료 확인

작업 branch·경로·시작 SHA·base 대비 차이, 생성 또는 재개 여부와 보존한 변경을 간결히 보고한다. 상태 확인만 하고 브랜치를 확보하지 못했으면 준비 완료라고 하지 않는다. 사용자가 상태 조회만 요청했다면 변경 없이 조회 결과를 보고한다.
