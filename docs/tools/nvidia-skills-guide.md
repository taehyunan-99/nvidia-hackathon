# NVIDIA 스킬 사용 기준

기존 `nvidia/docs/03-nvidia-github-skills.md`(조사일 2026-09-22)에서 필요한 개념과 설치 전 확인사항을 추려 2026-09-24 정리했다. 새 설치·실행 검증은 하지 않았다.

## 스킬이 제공하는 것

스킬은 `SKILL.md` 지침과 참조·스크립트를 코딩 에이전트에 제공한다.
모델 서버, GPU, API 계정이나 실제 업무 함수는 별도로 준비해야 한다.
설치된 개발용 스킬 수와 제출 제품이 실제 호출한 도구 수를 구분한다.

## 이 저장소에서 선택하는 순서

1. [HER2 설계](../topics/her2/agent-design.md)의 단계별 입력·산출물을 먼저 확인한다.
2. [HER2 도구 정리](her2-toolkit.md)에서 사용할 절차와 API·라이브러리를 구분한다.
3. 실제 계정 접근, 라이선스, 입력 조건, 응답 시간, 결과 판정 방법을 확인한다.
4. 팀에서 추가를 요청한 스킬만 [공통 설정](../collaboration/agent-setup.md)에 따라 등록한다.

참조 파일이 있는 스킬은 `SKILL.md`만 가져오면 의존성이 빠질 수 있다.
실제 사용하는 저장소 커밋, 스킬 이름, 제품 버전을 함께 기록한다.
스킬의 내부 `name`과 폴더 이름은 다를 수 있으므로 설치 시 원본을 확인한다.

## 조사 당시 출처

- [NVIDIA/skills 고정 스냅샷](https://github.com/NVIDIA/skills/tree/fd9f1466ff8a39178e488981e8b5118709392949)
- [BioNeMo Agent Toolkit 고정 스냅샷](https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit/tree/0e67a612e4045f007e38fa77adc8f3ebfc5616b6)

전체 제품 카탈로그와 다른 분야 설치 예시는 이번 팀 저장소 범위에서 제외했다.
