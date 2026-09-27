---
name: agent-evaluate
description: 사용자가 $agent-evaluate 또는 /agent-evaluate를 명시 호출하면 HER2 에이전트를 해커톤용 20점 루브릭과 10개 사례로 평가하고 근거·점수·한계를 기록한다.
---

# Agent Evaluate

[해커톤 평가 기준](../../../docs/topics/her2/hackathon-evaluation.md)과 적용 영역의 AGENTS.md를 읽는다. 데이터·실행기·채점기는 `docs/topics/her2/assets/hackathon-evaluation/`이 원본이다. 새 평가 플랫폼이나 제품 수정은 이 스킬의 범위가 아니다.

## 대상과 실행

- 현재 checkout의 branch·HEAD·변경 파일을 확인하고 평가할 버전을 기록한다. 다른 세션의 변경을 가져오거나 branch를 바꾸지 않는다. 최신 main 평가를 요청받았는데 현재 버전과 다르면 그 차이를 먼저 설명한다.
- `uv run --locked python docs/topics/her2/assets/hackathon-evaluation/score.py`로 고정 데이터의 해시·규격을 검사한다. 불일치하면 원인을 확인한다. 점수를 맞추려고 `prepare.py`로 기대값/잠금 파일을 덮어쓰지 않는다.
- 실행마다 새로운 `--out` 폴더를 사용한다. 기본 명령은 `uv run --locked python docs/topics/her2/assets/hackathon-evaluation/run.py --out <새-기록-폴더>`다. 10개 사례의 제품 로직·도구 관문을 오프라인으로 검사하며 모델 정확도 시험은 아니다.
- 실제 API 평가가 요청·승인된 범위에 있을 때만 `--live-reference`를 추가한다. 정상 입력의 NAT 실행 한 건(후보 2개)이므로 LLM 요청 한 번과 다르다. Boltz-2는 항상 대역이다. 키가 파일에만 있으면 `--credentials-file <로컬-env-경로>`를 사용하고 값을 출력·복사·기록하지 않는다. 반복·429 뒤 추가 실행은 승인된 횟수 안에서만 한다.
- 현재 실행기는 Boltz-2 실호출을 지원하지 않는다. 이를 요청받으면 별도 호출 범위와 실행 경로가 필요한 작업으로 구분한다.

## 판정과 기록

`cases.json`의 각 항목을 실행 자료로 확인하고 `scorecard-template.json`을 실행별로 복사해 채운다. 자동 수집기 `run.py`와 수동 근거 검토를 혼동하지 않는다. `harness_or_product_error`가 있으면 평가기 문제인지 제품 문제인지 구분한 뒤 관련 항목을 판정한다.

- 입력·출력·도구 기록으로 판정 가능한 항목과 실제 화면이 필요한 I2/S2를 구분한다. 화면을 열 수 없으면 미검증으로 남긴다. 코드만 보고 화면 검사를 통과시키지 않는다.
- 주제별 판정 원칙을 지킨다: 접촉은 검토 가능, 접근성·당쇄 영향은 미확인이면 별도 보류. 후보 전체 `completed`나 의견 enum 하나로 채점하지 않는다.
- 수치·단위·후보·구조·조건이 틀린 근거를 사용하는지 확인한다. 정상 성공이 잘못된 구조 사용·효능 단정·실패 은폐를 상쇄하지 못한다.
- `pass`/`fail`에는 검토자·commit·증거 파일과 위치를 남긴다. 수행하지 않은 항목은 `not_run`이며 총점을 계산하지 않는다. 이전 실행의 통과 항목을 현재 점수로 복사하지 않는다.
- `score.py --scorecard <채점표>`로 집계한다. 오프라인 점수, 실제 모델 관찰, 화면/DB 검증 범위를 별도로 보고한다. 20점은 내부 준비 점수이며 생물학적 정확도·대회 공식 점수가 아니다.

결과 문서에는 기준 commit·데이터 버전·실행 모드, 영역별 점수와 치명 실패, 증거 링크, 미검증 범위, 먼저 고칠 항목을 남긴다. 공개 입력과 재현 자료만 보존하고 인증정보를 포함하지 않는다. 같은 문제를 다시 확인하기 위한 최소 기록이면 충분하다.

## 경계

설치/수정 요청만으로 평가를 시작하지 않는다. 평가 요청은 기록 파일 생성을 포함하지만 커밋·push·제품 수정·대량 외부 호출을 포함하지 않는다. 기본 검증 명령은 `uv run --locked pytest docs/topics/her2/assets/hackathon-evaluation/test_score.py -q`다.
