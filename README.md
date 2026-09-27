# Bio-3

> **서비스 사이트:** [Bio-3 웹 서비스](https://d25wpps17lj0dn.cloudfront.net/)

**HER2 항체 후보를 근거부터 검토하는 해커톤 프로젝트.** 서열과 구조가 같은 후보를 가리키는지 확인하고, 자료 상태에 따라 공개 구조 재사용·구조 예측·판단 보류 중 다음 행동을 선택합니다. 결과 화면에서는 3D 구조, 검토 근거, 남은 질문을 함께 살펴볼 수 있습니다.

## 해결하려는 문제

항체 후보마다 서열, 실험 구조, 예측 구조와 출처가 흩어져 있으면 같은 조건에서 비교하고 있는지 확인하기 어렵습니다.

| 확인할 질문 | 놓치기 쉬운 문제 |
|---|---|
| **이 구조가 해당 후보의 것인가?** | 표적·항체 서열, 사슬 또는 분석 구간이 맞지 않으면 비교의 출발점이 달라집니다. |
| **무엇이 관측이고 무엇이 예측인가?** | 실험 구조와 모델 예측을 같은 수준의 근거로 다루면 결과를 과신할 수 있습니다. |
| **어느 판단을 보류해야 하나?** | 당쇄·주변 환경 자료나 계산 항목이 빠졌을 때 이를 ‘영향 없음’으로 해석할 수 없습니다. |

이 프로젝트는 후보별 입력·구조·출처를 연결하고, **확인된 사실·계산 결과·미확인 항목**을 나누어 다음 검토에 필요한 질문을 남깁니다.

## 검토 흐름

1. **입력 확인** — HER2와 항체 후보의 서열·사슬·구간을 구조 및 출처와 대조합니다.
2. **자료에 맞는 경로 선택** — NeMo Agent Toolkit(NAT) 에이전트가 허용된 도구 중 다음 행동을 고르고, 입력·실행 조건은 코드에서 검사합니다.
3. **구조 분석** — 확보한 좌표에서 접촉 잔기와 표면 지표 등을 계산하고, 사용한 구조 조건과 근거를 기록합니다.
4. **결과 검토** — 후보·조건별 3D 구조와 근거, 검토 의견, 보류 이유, 후속 질문을 화면과 JSON/CSV 보고서로 연결합니다.

| 자료 상태 | 다음 행동 |
|---|---|
| 일치하는 공개 실험 구조가 있음 | RCSB 구조를 재사용하고 새 예측을 생략한 이유를 기록 |
| 새 구조가 필요함 | NVIDIA Boltz-2로 예측하고 실험 구조와 다른 근거로 표시 |
| 입력 또는 근거가 부족함 | 해당 판단을 보류하고 빠진 자료와 이유를 표시 |

첫 화면에서 실험 구조 비교, 실험·예측 비교(기본), 예측·계산 보류의 세 카드를 선택합니다. 기본 입력은 Trastuzumab Fab(1N8Z)과 Trastuzumab Fab D185A(6BHZ)이며, HER2가 없는 항체 단독 출처 6BHZ의 서열로 복합체를 예측합니다. 기존 1N8Z·1S78 비교도 유지하고, 계산 보류 시나리오는 Fab37(3N85)을 추가합니다. 직접 입력은 후보 2–4개를 지원합니다. [데이터 출처·검증·해석 범위](docs/frontend-hosting/test-data.md)를 따릅니다. 구조 지표는 **실제 결합력·치료 효과의 순위가 아닙니다.**

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| 화면·3D | ![React](https://img.shields.io/badge/React-20232A?logo=react&logoColor=61DAFB) ![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white) ![Vite](https://img.shields.io/badge/Vite-646CFF?logo=vite&logoColor=white) ![Mol*](https://img.shields.io/badge/Mol%2A-3D_Viewer-384B6B) |
| API·분석 | ![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white) ![NeMo Agent Toolkit](https://img.shields.io/badge/NeMo_Agent_Toolkit-76B900?logo=nvidia&logoColor=white) |
| 모델 | ![Nemotron](https://img.shields.io/badge/Nemotron-76B900?logo=nvidia&logoColor=white) ![Boltz-2](https://img.shields.io/badge/Boltz--2-76B900?logo=nvidia&logoColor=white) |
| 저장·인프라 | ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white) ![Docker](https://img.shields.io/badge/Docker_Compose-2496ED?logo=docker&logoColor=white) ![Caddy](https://img.shields.io/badge/Caddy-1F88C0?logo=caddy&logoColor=white) |

코드는 `frontend/`(입력·비교·보고·3D), `service/`(API·저장·worker), `logic/`(에이전트·구조 분석), `docs/`(기획·검증 근거)로 나뉩니다.

## 팀

| 이름 | 담당 및 기여 | GitHub |
|---|---|---|
| 안태현 | **서비스 개발** — React 화면과 FastAPI·worker의 접수·결과 흐름, 분석 결과 연결과 배포 준비 | [@taehyunan-99](https://github.com/taehyunan-99) |
| 김희태 | **에이전트 개발** — NAT 에이전트와 NVIDIA 모델 호출, 오류 복구 및 실행 성능 검증 | [@kimheetae0104](https://github.com/kimheetae0104) |
| 조수빈 | **구조 분석** — 공개 구조의 서열·잔기 대응, 접촉·표면·관측 당 분석 | [@kongbeankong](https://github.com/kongbeankong) |
