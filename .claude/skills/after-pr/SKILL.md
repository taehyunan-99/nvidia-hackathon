---
name: after-pr
description: "사용자가 $after-pr 또는 /after-pr로 특정 병합 완료 PR을 명시할 때만 base를 확인하고 해당 작업의 브랜치와 승인된 임시 worktree를 정리한다."
disable-model-invocation: true
---

# 공통 after-pr 스킬 실행

먼저 [공통 원본](../../../.agents/skills/after-pr/SKILL.md)을 읽고 전체 절차를 따른다.
사용자 인자를 그대로 전달한다. 참조·스크립트·자산 경로는 이 wrapper가 아니라 공통 원본 폴더를 기준으로 해석한다.
이 파일은 진입점이며 실행 절차를 복제하지 않는다. 스킬 설치·검토 요청은 스킬 실행 요청으로 해석하지 않는다.
