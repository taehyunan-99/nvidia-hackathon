# HER2 항체 후보 검토 에이전트 설계

> 이전 기록: `nvidia/docs/24-her2-antibody-agent-design.md`에서 2026-09-24 이관. 아래 조사·작성 기준일을 유지하며 이번 이관에서 외부 사실이나 실행 결과를 재검증하지 않았습니다.
> 상태: 검토 중인 주제 후보. 이번 저장소에 남긴 유일한 주제이며 최종 선정·구현 완료를 뜻하지 않습니다.

작성일: 2026-09-24

## 목적과 입력

**HER2와 항체 후보를 받아, 결합 부위·접근성·구조상 문제를 비교하고 다음 실험 후보를 제시하는 에이전트**로 설계한다.

입력은 **HER2 ID/서열 + 비교할 항체 2~3개의 중쇄·경쇄 FASTA + 선택적 구조 파일**이다.

## 에이전트 구성

전체 판단은 **[Nemotron 3 Nano](https://build.nvidia.com/nvidia/nemotron-3-nano-30b-a3b) + [NeMo Agent Toolkit(NAT)](https://github.com/NVIDIA/NeMo-Agent-Toolkit)**가 담당한다.

NVIDIA 스킬의 실행 절차를 참고해 API 호출·파일 검증을 NAT 함수로 연결한다. 스킬 설치만으로 이 연결이 자동 완성되지는 않는다.

## 단계별 스킬·도구와 판단 분기

| 단계 | 사용할 스킬·도구 | 수행 작업과 출력 | 에이전트의 판단 분기 |
|---|---|---|---|
| **① 입력·자료 확보** | **UniProt REST**, **RCSB PDB Search/Data API**, **Thera-SAbDab**, **Biopython** | HER2의 세포외 영역, 항체 서열, 실험 구조 수집; 서열·사슬·잔기 번호 대응표 생성 | 입력과 맞는 실험 구조가 있으면 활용 → 없으면 예측 대상으로 등록; 서열 불일치는 먼저 해결 |
| **② 결합 후보 부위 검토** | **[FreeSASA](https://freesasa.github.io/)**, **Biopython**, 선택적으로 **IEDB Query API** | 표면 노출도 계산, 기존 항체의 접촉 잔기 확인, 알려진 당쇄·주변 구조와 대조; 부위별 근거표 생성 | 실험으로 알려진 epitope와 계산상 후보를 구분; 구조가 누락된 부위는 판단 보류 |
| **③ 필요한 복합체 예측** | **[msa-search-nim](https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit/blob/main/nim-skills/msa-search-nim/SKILL.md)** → **[boltz2-nim](https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit/blob/main/nim-skills/boltz2-nim/SKILL.md)** | 필요할 때 HER2의 MSA 확보 → HER2 세포외 영역과 항체 사슬들을 입력 → 복합체 **mmCIF·구조 신뢰도** 저장 | 기존 결과·실험 구조로 충분하면 계산 생략; 예측이 불안정하면 제한된 재실행 또는 보류 |
| **④ 후보별 검증·비교** | **[Biopython](https://biopython.org/docs/latest/api/Bio.PDB.html)**의 `NeighborSearch`, `Superimposer` + **NumPy** + 직접 작성할 검사 함수 | 접촉 잔기, 원자 간 충돌, 구조 정렬, 여러 예측에서 결합 자세의 일관성 비교 | 높은 신뢰도라도 충돌·서열 오류가 있으면 보류; 지표가 충돌하면 한 점수로 숨기지 않고 이유 표시 |
| **⑤ 결과·실행 기록 제공** | **[Mol*](https://molstar.org/)**, **NAT 실행 추적**, JSON/CSV 저장 | 3D 비교 화면, 후보별 검토표, 출처, 사용한 입력·모델 설정, 추가 실험 항목 | 자료가 충분한 후보만 검토 우선순위 제시; 미확인 항목은 결과에 유지 |

## 직접 구현할 기능과 차별점

- **직접 구현할 도구 함수**: 자료 조회, 잔기 번호 대응, 표면·접촉 계산, NIM 실행, 후보 비교·보고서 생성.
- **에이전트다운 동작**: “구조가 있으니 예측 생략”, “서열이 다르니 먼저 확인”, “당쇄 정보가 부족하니 추가 조회”, “결과가 불안정하니 추천 보류”.
- **수치 출력**: 표면 노출 면적, 접촉 잔기 목록·수, 충돌 지표, 구조 신뢰도, 실험 구조 대비 편차 — **항체 결합력이나 부작용 확률과 구분**.
- **차별점**: 같은 후보를 **분리된 HER2 구조에서 검토한 결과와, 확보된 당쇄·주변 구조까지 반영한 결과**로 비교하고 판단이 바뀐 이유를 표시.

## 최소 데모와 검증

HER2 + 트라스투주맙·퍼투주맙의 공개 구조([1N8Z](https://www.rcsb.org/structure/1N8Z), [1S78](https://www.rcsb.org/structure/1S78))로 번호 대응·접촉 부위 재현을 검증하고, 별도의 오류 입력으로 검증·보류 분기를 확인한다.

첫 구현은 **공개 구조 분석 경로와 Boltz-2 호출 한 건**부터 확인한다.

현재는 문서상 연결 가능성을 확인한 설계 단계이며, 실제 계정의 API 접근·소요 시간·항체 복합체 결과 품질은 아직 검증해야 한다.
