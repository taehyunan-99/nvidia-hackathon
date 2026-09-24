---
name: handoff
description: "명시 호출된 init, next, done, pause, start, inspect로 검증된 작업을 세션 사이에 인계한다. 별도 Codex 앱 작업을 명시 요청한 경우에만 병렬 인수인계를 운영한다."
disable-model-invocation: true
---

# 공통 handoff 스킬 실행

먼저 [공통 원본](../../../.agents/skills/handoff/SKILL.md)을 읽고 전체 절차를 따른다.
사용자 인자를 그대로 전달한다. 참조·스크립트·자산 경로는 이 wrapper가 아니라 공통 원본 폴더를 기준으로 해석한다.
이 파일은 진입점이며 실행 절차를 복제하지 않는다. 스킬 설치·검토 요청은 스킬 실행 요청으로 해석하지 않는다.
