# NVIDIA 에이전트와 실행 프레임워크

> 이전 기록: `nvidia/docs/09-nvidia-agents.md`에서 2026-09-24 이관. 아래 조사·작성 기준일을 유지하며 이번 이관에서 외부 사실이나 실행 결과를 재검증하지 않았습니다.

기준일: 2026-09-22. **NemoClaw·OpenShell은 대회 안내 명시**, NAT·Relay·Fabric 등은 기술 후보이며 대회 필수 여부는 미확인이다.

## NemoClaw: 지원 에이전트의 실행 스택

공식 저장소는 NemoClaw를 OpenShell 안에서 지원 에이전트를 실행하는 오픈소스 참조 스택으로 설명한다.
현재 README는 기본 OpenClaw 외 Hermes, LangChain Deep Agents Code를 나열한다.
설정 안내, 추론 연결, 네트워크 정책, 통합 관리, snapshot, lifecycle 작업을 제공한다.
**모델 이름도, 독립적인 새 LLM도 아니다.** [공식 저장소](https://github.com/NVIDIA/NemoClaw)

| 구성 | 무엇을 담당하나? |
|---|---|
| OpenClaw 등 지원 에이전트 | 대화·작업 실행·해당 에이전트의 도구 사용 |
| NemoClaw | 에이전트 설정과 통합·운영 절차 |
| OpenShell | 격리된 실행과 정책 집행 |
| 추론 공급자 | Nemotron 등 모델의 응답 |

**분석:** 파일·셸·메시징·여러 도구를 사용하는 개인 비서형 데모의 출발점이 될 수 있다.
그러나 설치만으로 특정 산업 문제의 데이터 연결과 완료 조건이 만들어지지는 않는다.
공식 저장소는 alpha 프로젝트임을 명시한다. 버전 고정과 실제 동작 확인이 중요하다.

## OpenShell: 에이전트가 실행할 수 있는 범위를 관리

OpenShell은 sandbox와 파일·네트워크·프로세스 정책을 제공한다.
최신 README에는 HTTP method/path 단위 네트워크 정책과 endpoint에 결합된 자격증명 주입이 설명되어 있다.
Windows는 WSL2 경로가 experimental로 표시된다.
README의 `main`에는 0.1.0 준비 안내가 있어 **개발 문서와 안정 릴리스 기능이 일치한다고 가정하면 안 된다.** [공식 저장소](https://github.com/NVIDIA/OpenShell)

**분석:** 읽기 전용 검색, 지정 디렉터리 쓰기, 허용된 API만 호출하는 데모 구조에 활용할 수 있다.
잘못된 답변·잘못된 수식·불충분한 근거는 sandbox가 해결하지 않는다.
에이전트 프롬프트의 “하지 마라”와 운영체제·네트워크 수준의 차단을 구분해 설계한다.

## NeMo Agent Toolkit: 직접 만드는 에이전트의 조립·측정

NAT는 여러 프레임워크와 Python 도구를 연결하고 에이전트 실행을 관찰·평가·최적화하는 라이브러리다.
LangChain/LangGraph, LlamaIndex, CrewAI 등과 함께 사용할 수 있으며 MCP와 A2A도 지원한다.
배포된 모델을 호출하는 구성이라면 orchestration 자체 때문에 로컬 GPU가 필요한 것은 아니다.
공식 README의 Python 지원 범위는 3.11~3.13이다. [NAT 저장소](https://github.com/NVIDIA/NeMo-Agent-Toolkit)

| 기능 | 해커톤에서 확인할 수 있는 가치 |
|---|---|
| 함수·도구 등록 | 실제 업무 API·검색·계산을 에이전트가 호출 |
| 워크플로 구성 | 목표에 따른 실행 순서·상태 관리 |
| 관찰·프로파일링 | 어느 단계가 느리거나 실패했는지 확인 |
| 평가기 | 정답·신뢰성·완료 시간 비교 |
| MCP 서버/클라이언트 | 기존 도구 재사용 또는 에이전트를 도구로 노출 |

전체 workflow를 대상으로 하는 `nat eval`은 별도 평가 의존성이 필요하다.
로그가 있다는 것과 정답·완료 여부를 평가했다는 것은 다르다. [공식 평가 문서](https://docs.nvidia.com/nemo/agent-toolkit/latest/workflows/evaluate.html)

## 어느 경로를 택할지 — 분석

| 하고 싶은 일 | 우선 살펴볼 경로 | 이유 |
|---|---|---|
| 도메인 도구 2~3개를 연결한 서비스 | NAT 또는 간단한 Python tool loop | 입력·출력·평가를 직접 통제하기 쉬움 |
| 기존 범용 에이전트에 업무 환경 제공 | NemoClaw + 지원 에이전트 | 도구 실행과 sandbox 운영을 재사용 |
| 웹·문서 심층 조사 | AI-Q Blueprint | 조사 흐름을 재사용 가능 |
| 영상 질의·검색 | VSS Blueprint | 영상 처리와 에이전트 도구를 함께 제공 |
| 기존 앱에 실행 관찰 추가 | Relay | 호출을 관찰·제어하는 계층 활용 |
| 여러 harness 실행을 통합 | Fabric | 실행·결과의 공통 SDK 계약 활용 |

여러 에이전트를 사용하는 것이 단일 에이전트보다 자동으로 우수하지는 않다.
분담으로 얻는 이익이 추가 지연·비용·오류 전달보다 클 때 확장한다.
대회가 특정 실행 스택을 요구하는지는 [미확인 규정](../hackathon/requirements.md)을 먼저 확인해야 한다.
