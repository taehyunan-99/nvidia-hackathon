---
name: task-workflow
description: 사용자가 $task-workflow 또는 /task-workflow를 명시 호출할 때만 팀 저장소의 원격 main·현재 변경·작업 위치를 확인하고 요청한 Git 작업을 준비한다. 현재는 main 직접 작업이 기본이며 브랜치·worktree는 요청할 때만 만든다.
---

# Task Workflow

[CONTRIBUTING.md](../../../CONTRIBUTING.md)와 적용되는 AGENTS.md를 먼저 읽는다.
현재 팀은 `main`에서 직접 작업한다. 별도 브랜치·PR 운영은 요청한 작업에만 적용한다.
회사 프로젝트 ID, develop, Windows SID, 고정 worktree 등록부나 외부 PowerShell 스크립트를 요구하지 않는다.
명령은 현재 운영체제의 Git과 필요한 경우 GitHub CLI/API로 실행한다.

## 작업 상태 확인

1. 정확한 Git 루트, `git status --short`, 현재 브랜치, `git worktree list --porcelain`, origin URL을 확인한다. 다른 checkout이나 다른 팀원 변경을 현재 작업으로 가져오지 않는다.
2. origin이 있으면 `git fetch origin --prune`을 실행하고 원격 main의 SHA를 한 번 확정한다. fetch 실패를 원격 변경 없음으로 해석하지 않는다. HEAD나 원격 main이 없는 최초 저장소는 그 상태를 명시하고 존재하지 않는 ref를 비교하지 않는다.
3. 로컬 main과 원격 main의 ahead/behind를 확인한다. 기록할 작업 설명은 대화에 간결히 보고하며 별도 실행 리포트 파일은 만들지 않는다.
4. 현재 미커밋 변경의 소유자와 요청 범위를 확인한다. 같은 작업의 변경은 보존하며 이어간다. 다른 사람의 변경이 있으면 자동 stage·stash·reset·checkout하지 않는다.

## 기본: main에서 계속 작업

- 이미 main이면 새 세션·새 작업이라는 이유로 브랜치를 만들지 않는다.
- main이 원격보다 뒤처졌으면 차이를 보고한다. **main 최신화까지 요청된 경우에만**, checkout이 clean이고 fast-forward 관계임을 확인하고 갱신 직전 branch·HEAD·clean 상태를 다시 확인한 뒤 `git merge --ff-only <verified-main-sha>`로 갱신한다. 단순 상태 확인·작업 준비 요청만으로 checkout을 갱신하지 않는다.
- 미커밋 변경이 있거나 로컬과 원격이 갈라졌으면 자동 pull·rebase·merge하지 않는다. 겹치는 변경과 상태를 먼저 확인해 필요한 결정만 묻는다.
- main이 원격보다 앞서 있어도 기존 커밋을 보존한다. 작업 시작 요청만으로 push하지 않는다.
- 다른 branch 또는 detached checkout이면 자동 전환하지 않는다. 현재 작업을 이어가는지, main으로 돌아가는지 모호한 경우 확인한다.

## 선택: 작업 브랜치 또는 worktree를 요청한 경우

1. 이름과 목적, PR 대상 base는 main임을 확정하고 **새 작업 시작**인지 **main에 이미 커밋한 작업의 PR 전환**인지 구분한다. 기존 브랜치가 있으면 정확한 head의 PR 상태와 현재 작업의 동일성을 확인한다. 병합된 PR 브랜치에는 새 작업을 이어 쓰지 않는다. PR 조회 실패를 미병합으로 간주하지 않는다.
2. clean 상태의 현재 checkout에 요청한 새 브랜치를 둘지, 독립 작업을 위해 사용자가 지정·승인한 별도 경로에 linked worktree를 둘지 정한다. 실제 생성은 다음 단계의 시작 SHA 검토 후 수행한다. 다른 worktree가 사용 중인 브랜치를 강제로 checkout하지 않는다.
3. 시작 SHA는 목적에 맞게 고정하고 생성 직전에 원본 branch·HEAD·작업 상태를 다시 확인한다. 달라졌으면 범위를 재검토한다.
   - 새 작업은 검증한 원격 main SHA에서 시작한다.
   - 기존 main 작업의 PR 전환을 명시 요청했다면 로컬 main SHA를 고정하고 원격 main과의 커밋 목록·diff를 검토한다. 원격 base가 로컬 main의 조상이고 앞선 커밋 전부가 요청 범위이면 그 **로컬 main SHA**에서 요청한 새 branch/worktree를 만든다. 다른 작업이 섞였거나 이력이 갈라졌으면 포함할 커밋과 분리 방법을 먼저 확인하며, 전체를 무조건 옮기지 않는다.
   - 생성 후 경로·공통 Git 디렉터리·branch·HEAD와 PR 예정 diff를 확인한다. 원본 main과 진행 중인 작업·미커밋 변경은 보존하며, main을 reset하거나 force push하지 않는다. 원본 main을 보존한 상태에서 squash/rebase 병합하면 이후 main이 원격과 갈라질 수 있으며, 이 경우 after-pr는 자동 복구하지 않고 별도 정리 판단을 요청한다.
4. 새 Codex 앱 세션을 만드는 기능은 이 스킬의 범위가 아니다. 별도 요청한 병렬 handoff는 [handoff](../handoff/SKILL.md)의 앱 식별·worktree 등록·실행 종료 검증을 사용한다.

## 커밋·push·PR·정리 경계

- 커밋은 요청된 변경을 의미 있는 단위로 묶고, [commit](../commit/SKILL.md)의 선택 stage·검증 원칙을 따른다. 진행 기록용 빈 커밋·자동 이력 정리는 하지 않는다.
- 명시적인 커밋·push 요청이 있어야 실행한다. main 직접 push는 현재 팀 방식에 허용되지만 hook·원격 보호 규칙을 우회하거나 force push하지 않는다.
- [pull-request](../pull-request/SKILL.md)는 작업 브랜치 PR을 요청할 때만 사용한다. main 직접 작업에 PR을 강요하지 않는다.
- base가 앞섰다는 이유로 커밋 전후에 자동 통합하지 않는다. PR 범위의 충돌·관련 변경을 확인하고 통합이 필요한 경우 별도로 처리한다.
- 병합 후 정리는 명시 호출된 [after-pr](../after-pr/SKILL.md)가 맡는다. 작업 시작을 이유로 branch·worktree를 삭제하지 않는다.
- 실패한 Git 작업은 실제 명령·경로·오류를 확인하고 보존한다. 변경 중인 대상의 상태를 재확인하기 전 같은 변경 명령을 반복하지 않는다.

## 완료 확인

현재 branch·작업 위치, 원격 main과의 차이, 보존한 미커밋 변경과 다음 동작만 간결히 알린다.
작업 준비만 요청됐다면 소스 수정·커밋·push·PR·정리는 하지 않는다.
