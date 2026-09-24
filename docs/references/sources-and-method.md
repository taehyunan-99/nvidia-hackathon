# 출처와 검증 범위

2026-09-24 선별 이관. 원본은 `nvidia/docs/16-sources-method.md`(2026-09-22 조사) 및 각 문서에 표시한 조사 기록이다.
이번 작업은 기존 기록을 분류·편집한 것이며 행사 조건·모델 성능·계정 접근을 새로 검증한 작업은 아니다.

## 사실을 읽는 기준

- 공식 확인: 당시 주최 측 자료, NVIDIA 공식 문서·모델 카드·저장소에서 확인한 내용.
- 분석·제안: 자료를 바탕으로 작성한 설계나 준비 기준. 공식 배점으로 해석하지 않는다. 현재 팀의 프로젝트 범위는 [프로젝트 개요](../topics/her2/overview.md)에서 확인한다.
- 미검증: API 접근·한도·소요 시간·실제 품질·데모 재현성은 실행 증거가 있어야 확인된다.

## 먼저 확인할 근거

| 목적 | 팀 문서 | 원출처 |
|---|---|---|
| 대회 규정 | [요구사항](../hackathon/requirements.md) | [주최 안내](https://fastcampus.co.kr/NVIDIA_hackathon) |
| 실제 제출 필드 | [신청 폼 스냅샷](../hackathon/application-form.md) | 문서에 기록된 공식 Google Form |
| 지정 교육 | [강의 노트](../hackathon/nemoclaw-course-notes.md) | [DLI 강의](https://nvdli.github.io/NemoClawDLI/nemoclaw/index.html) |
| 에이전트 실행·관측 | [프레임워크](../tools/agent-frameworks.md) | [NAT](https://github.com/NVIDIA/NeMo-Agent-Toolkit), [NemoClaw](https://github.com/NVIDIA/NemoClaw), [OpenShell](https://github.com/NVIDIA/OpenShell) |
| 모델·API | [모델과 NIM](../tools/models-and-nim.md) | [Build](https://build.nvidia.com/explore/discover), [NIM](https://docs.api.nvidia.com/nim/docs/overview) |
| 단백질 도구·데이터 | [HER2 도구](../tools/her2-toolkit.md) | 문서 내 BioNeMo·PDB·UniProt 및 도구별 링크 |

원본 16번 문서는 신청서를 로그인 화면까지만 확인했다고 기록했으나, 추가 이관된 신청 폼 문서는 2026-09-20 공개 질문 정의를 별도로 기록했다.
확인 범위가 다른 기록이므로 실제 제출 전에 폼을 다시 확인한다. 신청 완료나 규정 확정을 의미하지 않는다.

## 유지할 정보

문서를 갱신할 때 확인일, 원출처, 버전·커밋, 실행 여부, 남은 불확실성을 함께 적는다.
`main`·`latest` 및 API 카탈로그는 변하므로 구현 시 실제 사용 버전으로 다시 확인한다.
구조 신뢰도·접촉 지표를 실험적 항체 결합력이나 치료 효능으로 바꾸어 표현하지 않는다.
문서 이관 범위와 제외 이유는 [선별 기록](document-selection.md)을 참고한다.
