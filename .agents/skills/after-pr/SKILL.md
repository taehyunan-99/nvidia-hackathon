---
name: after-pr
description: 사용자가 $after-pr 또는 /after-pr로 특정 병합 완료 PR을 명시할 때만 base를 확인하고 해당 작업의 브랜치와 승인된 임시 worktree를 정리한다.
---

# After PR

[팀 규칙](../../../CONTRIBUTING.md)과 적용되는 AGENTS.md를 읽는다.
명시 호출은 식별된 병합 완료 PR의 작업 브랜치 정리를 허용한다. 다른 작업·고정 worktree·미커밋 파일에는 적용하지 않는다.
일반 Git과 GitHub CLI/API를 사용하며 회사의 PowerShell 도구·develop·고정 경로를 요구하지 않는다.

## 읽기 전용 사전 확인

1. 인자의 PR 번호 또는 정확한 head branch로 PR 하나를 확정한다. 대상이 모호하면 질문한다. `git worktree list --porcelain`과 origin URL로 주 checkout·연결 worktree를 확인한다.
2. GitHub에서 `state=MERGED`, 동일 저장소 head, `baseRefName=main`, 정확한 head branch, 전체 head SHA와 mergeCommit SHA를 가져온다. fork PR, main 자체, 확인할 수 없는 head 또는 merge SHA는 삭제하지 않는다.
3. `git fetch origin --prune`을 성공한 뒤 `origin/main`의 SHA를 고정한다. mergeCommit SHA가 이 base의 조상인지 확인한다. squash/rebase merge에서는 head SHA가 main의 조상일 필요가 없으므로 그 조건을 혼동하지 않는다.
4. 남아 있는 로컬 작업 브랜치와 정확한 원격 ref `refs/heads/<branch>`의 tip이 검증한 PR head SHA와 같은지 각각 확인한다. 로컬 tip이 일치하면 해당 저장소의 로컬 설정 중 정확한 `branch.<branch>` 섹션도 기록한다. ref가 이미 없으면 해당 ref는 이미 완료로 기록하되 남은 설정의 소유권까지 추정하지 않는다. 병합 후 커밋이 추가됐거나 대상이 달라졌으면 아무것도 삭제하지 않는다.
5. worktree의 수정·untracked·ignored 파일, 사용 중인 세션과 작업을 확인한다. 파일이나 작업이 남으면 보존한다. 임시라는 근거가 없는 worktree와 주 checkout은 삭제하지 않는다.

## base 동기화와 정리

1. main이 체크아웃된 경로가 있으면 clean 상태와 로컬 main이 고정한 원격 base의 조상인지 다시 확인한 후 그 경로에서 `git merge --ff-only <verified-base-sha>`로 동기화한다. diverged·dirty 상태에서는 중단한다. 다른 팀원의 checkout 브랜치를 변경하지 않는다.
2. 현재 사용자가 정리를 요청한 checkout이 작업 브랜치에 있다면, 파일·세션 안전을 확인한 뒤 main으로 전환한다. 다른 worktree에서 main을 이미 사용 중이면 검증한 base SHA로 detach할 수 있다. main으로 전환한 경우 clean 상태·조상 관계를 다시 확인하고 `git merge --ff-only <verified-base-sha>`로 반드시 동기화한다. 고정 worktree 경로는 보존한다.
3. 사용자가 임시로 생성·정리하도록 지정한 해당 작업의 linked worktree만, 주 checkout 밖에서 `git worktree remove <path>`로 제거한다. `--force`는 쓰지 않는다. 용도가 불명확하면 브랜치 삭제 전 확인한다.
4. 모든 worktree에서 해당 브랜치가 해제되었는지 확인한다. 로컬 ref의 tip을 다시 비교하고 `git update-ref -d refs/heads/<branch> <verified-head-sha>`로 정확히 검증한 ref만 삭제한다. 이 비교 후 삭제 방식은 squash 병합에도 적용된다. main이나 임의 SHA에는 사용하지 않는다.
   - ref 삭제 성공 후 해당 ref가 여전히 없고 관련 쓰기 작업이 없으며 로컬 `branch.<branch>` 설정이 사전 기록과 같은지 확인한다. 섹션이 남아 있으면 `git config --local --remove-section "branch.<branch>"`으로 그 섹션만 제거하고 부재를 검증한다. 전역·다른 브랜치·출처가 다른 설정은 변경하지 않는다.
   - ref 삭제와 설정 삭제는 원자적 작업이 아니다. 브랜치 재생성·설정 변경·동시 쓰기가 확인되거나 이미 사라진 ref의 설정 소유권을 확인할 수 없으면 설정을 보존하고 미완료로 보고한다. 재시도에서도 확인된 소유권·SHA·설정 기록 없이 남은 섹션을 지우지 않는다.
5. 원격 브랜치가 남았으면 정확한 ref를 다시 읽고 PR head SHA와 일치할 때만 `git push --force-with-lease=refs/heads/<branch>:<verified-head-sha> origin :refs/heads/<branch>`로 삭제한다. 이 lease는 확인 이후 생긴 새 커밋을 보호하는 삭제 전용 비교 조건이며 일반 force push를 허용하지 않는다. 서버가 거절하면 우회하지 않는다.
6. base 상태, 보존 대상 worktree, 로컬 ref와 해당 로컬 설정 섹션의 부재, 정확한 원격 ref 부재를 확인한다. 이미 삭제된 항목은 다시 만들지 않는다. 실패 시 남은 ref·설정·worktree를 보고하고 재시도에서도 같은 PR과 SHA 조건을 다시 확인한다.

## 보고

PR·branch, base 동기화, 완료·이미 완료·보존·미완료 항목을 보고한다.
모든 요청된 정리 조건을 검증했을 때만 완료라고 한다. 일부 실패는 `AFTER_PR_INCOMPLETE`와 이유를 남긴다.
자동 stash, reset --hard, git clean, 파일 강제 삭제, 고정 worktree 제거는 하지 않는다.
