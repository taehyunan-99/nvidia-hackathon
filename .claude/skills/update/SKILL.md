---
name: update
description: "명시 호출 시 사용자 인터뷰로 영역 가이드를 갱신하고 충돌을 확인한다. 영역 재구성은 --restructure로 별도 요청한다."
disable-model-invocation: true
---

# 공통 update 스킬 실행

먼저 [공통 원본](../../../.agents/skills/update/SKILL.md)을 읽고 전체 절차를 따른다.
사용자 인자를 그대로 전달한다. 참조·스크립트·자산 경로는 이 wrapper가 아니라 공통 원본 폴더를 기준으로 해석한다.
이 파일은 진입점이며 실행 절차를 복제하지 않는다. 스킬 설치·검토 요청은 스킬 실행 요청으로 해석하지 않는다.
