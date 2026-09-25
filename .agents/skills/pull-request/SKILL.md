---
name: pull-request
description: 사용자가 $pull-request 또는 /pull-request를 명시 호출할 때만 작업 브랜치와 검증 결과를 확인하고 push한 뒤 PR을 생성하거나 갱신한다.
---

# Pull Request

[팀 규칙](../../../CONTRIBUTING.md), 적용되는 AGENTS.md와 [PR 템플릿](../../../.github/pull_request_template.md)을 읽는다.
원격은 현재 checkout의 origin에서 확인한다. 회사 저장소·계정·프로젝트 ID를 가정하지 않는다.

1. 커밋과 PR을 함께 요청했고 의도한 변경이 미커밋이면 commit 스킬부터 수행한다. PR 요청만으로 미커밋 변경을 임의 커밋하지 않는다.
2. `git fetch origin --prune`에 성공한 뒤 저장소 경로·origin URL·작업 브랜치·clean 상태를 확인하고 원격 base `main`과 HEAD의 전체 SHA를 고정한다. main 또는 detached HEAD에서 PR을 만들지 않는다. main의 기존 커밋을 PR로 전환하려는 경우 [작업 브랜치 전환 절차](../task-workflow/SKILL.md#작업-브랜치-생성과-전환)를 안내하며, 요청한 전환을 완료한 후 PR 검토를 다시 시작한다. 앞서 task-workflow 실행으로 승인된 해당 작업의 브랜치 전환은 재확인 없이 수행한다. PR 단독 요청을 새로운 전환 승인으로 간주하지 않으며 main을 되돌리지 않는다. 빈 원격에 main이 없으면 초기 커밋·기본 브랜치 게시를 별도 요청으로 완료해야 한다고 설명한다.
3. `git diff <verified-base-sha>...<verified-head-sha>`와 같은 SHA 기준의 커밋 목록으로 PR 전체 범위를 확인한다. base가 앞섰다는 이유만으로 자동 rebase·merge하지 않는다. 충돌·계약 변경이 있으면 깨끗한 작업 브랜치에서 필요한 통합 방법을 먼저 정한다. 공유 이력을 다시 쓰지 않는다.
4. 제목은 CONTRIBUTING.md의 Conventional Commits 형식으로 쓴다. 본문은 현재 템플릿의 변경 목적·주요 변경·검증·관련 이슈·확인 항목을 채운다. 실제 변경 전후와 실행한 검사, 미검증 이유를 간결히 적는다.
5. 검사 도구가 없는 현재 저장소에서는 형식·본문·diff를 직접 검토한다. 회사 전용 PR validator를 요구하지 않는다. 브랜치 준비가 이미 끝났으면 task-workflow를 중복 실행하지 않는다. 본문은 임시 UTF-8 파일에 실제 줄바꿈으로 작성하고 `--body-file`을 사용한다.
6. 명시적인 PR 생성·갱신 요청은 해당 작업 브랜치의 일반 push를 포함한다. 직전에 저장소·origin·branch·HEAD·clean 상태를 다시 확인하고 검토 시점과 다르면 범위와 본문을 재검토한다. `git push origin <verified-head-sha>:refs/heads/<branch>`처럼 검토한 SHA와 정확한 목적 ref를 지정한다. 정상 push가 거절되면 이유를 확인하고 중단하며 force push나 hook 우회를 하지 않는다. 기존 동일 저장소·head/base PR을 조회해 중복 생성을 피한다.
7. push 후와 PR 게시 직전에 정확한 원격 head ref를 읽어 검토한 SHA와 같은지 확인한다. 다르면 게시를 중단하고 차이를 보고한다. 완료된 변경은 Ready for review, 미완료 변경이나 사용자 Draft 요청은 Draft로 게시한다. 초안 상태를 임의 Ready로 승격하지 않는다. 앱 도구 또는 `gh pr create`/`gh pr edit`에 저장소·base·head 또는 확정한 PR 번호를 명시해 요청한 PR만 게시한다.
8. 게시 후 URL·baseRefName·headRefName·headRefOid·isDraft를 다시 조회하고 `headRefOid`가 검토한 전체 SHA와 같은지 대조한다. Codex 앱에서 attach_artifact 도구가 있으면 생성·작업한 PR을 현재 작업에 연결한다. SHA 불일치면 게시 완료로 보고하지 않고 이미 게시된 URL과 변경된 SHA·미검증 범위를 알린다. 자동 재push·PR 닫기·병합·브랜치 삭제는 하지 않는다.
