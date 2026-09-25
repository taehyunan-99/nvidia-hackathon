---
name: commit
description: 사용자가 $commit 또는 /commit을 명시 호출할 때만 현재 저장소의 규칙과 staged 변경을 확인하고 범위를 지정해 Git 커밋을 만든다.
---

# Commit

[팀 규칙](../../../CONTRIBUTING.md)과 적용되는 AGENTS.md를 먼저 읽는다. 모든 경로는 저장소 루트 기준으로 해석한다.

1. `git status --short`, 브랜치, 의도한 diff, 현재 staged diff를 확인한다. 이 호출은 커밋 생성만 허용하며 push·PR·병합을 허용하지 않는다.
2. 기본 base는 `main`. origin이 있으면 `git fetch origin --prune` 후 base와 현재 이력을 확인한다. fetch 실패 시 원인을 보고하고 커밋을 보류한다. base가 앞서 있어도 자동 merge·rebase·stash·이력 정리는 하지 않는다.
3. HEAD가 없는 최초 저장소는 초기 커밋으로 처리한다. 빈 원격의 `origin/main` 부재는 오류가 아니며 비교·diff에 존재하지 않는 HEAD를 쓰지 않는다. 일반 작업은 작업 브랜치에서 커밋한다. main 직접 커밋은 사용자가 명시한 예외에만 허용한다. 앞서 task-workflow 실행으로 승인된 해당 작업의 브랜치 준비가 남았다면 그 절차를 완료한 뒤 커밋한다. commit 호출만으로 브랜치·worktree를 임의 생성하지 않는다.
4. 요청한 파일만 `git add -- <path...>`로 stage한다. `git add .`와 `git add -A`로 다른 작업을 포함하지 않는다. 기존 staged 항목 중 범위 밖 파일이 있으면 임의 unstage·포함하지 말고 확인한다.
5. `git diff --cached --name-only`, `git diff --cached`, `git diff --cached --check`로 최종 범위를 검토한다. 비밀키·캐시·다른 팀원 변경을 포함하지 않는다. 빈 커밋을 만들지 않는다.
6. 변경에 필요한 검증만 실행하고 실제 결과와 미검증 항목을 구분한다. 문서·설정 작업에 존재하지 않는 앱 테스트를 요구하지 않는다.
7. 메시지는 CONTRIBUTING.md의 `<type>(<scope>): <summary>`를 따른다. scope는 선택이며 한국어·영어 모두 가능하다. 범용 영역명(docs, skills 등)을 쓰고 회사 프로젝트 ID를 요구하지 않는다.
8. 커밋 후 SHA·포함 파일·남은 변경을 확인한다. amend·push·PR은 별도 요청 없이는 하지 않는다. 사용자가 커밋과 PR을 함께 요청했으면 완료 후 pull-request 스킬로 이어간다.
