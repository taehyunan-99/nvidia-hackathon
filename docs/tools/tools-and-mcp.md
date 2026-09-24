# NVIDIA 도구·MCP·평가 도구

> 이전 기록: `nvidia/docs/11-nvidia-tools-mcp.md`에서 2026-09-24 이관. 아래 조사·작성 기준일을 유지하며 이번 이관에서 외부 사실이나 실행 결과를 재검증하지 않았습니다.

기준일: 2026-09-22. 이 문서는 실제 작업을 수행하는 도구를 어떻게 연결하는지 정리한다.

## 도구가 제공하는 실제 기능

| 도구/제품 | 연결 형태 | 입력 → 출력 | 직접 구현할 부분 |
|---|---|---|---|
| NIM | 모델별 HTTP/gRPC 등 | 입력 → 추론 결과 | 모델 선택·호출·오류 처리 |
| Retriever | CLI·Python·서비스·MCP | 문서/질의 → 근거 | 문서 확보·접근 제어 |
| cuOpt | Python·C·CLI·REST, 문제별 차이 | 수식·행렬 → 해 | 조건 추출·검증·지도 데이터 |
| VSS | 프로파일별 API·agent tools | 영상·조건 → 분석 | 소스 연결·사건 정의 |
| Data Designer | Python 및 별도 서비스 경로 | 스키마 → 합성 데이터 | 검증 규칙·기준 데이터 |
| 일반 Python 함수 | NAT 등록 또는 직접 tool loop | 구조화된 인자 → 업무 결과 | 업무별 코드 전체 |

근거: [NAT](https://github.com/NVIDIA/NeMo-Agent-Toolkit), [Retriever MCP](https://github.com/NVIDIA/skills/blob/fd9f1466ff8a39178e488981e8b5118709392949/skills/nemo-retriever-mcp/SKILL.md), [cuOpt](https://docs.nvidia.com/cuopt/user-guide/latest/), [Data Designer](https://github.com/NVIDIA-NeMo/DataDesigner).

## MCP가 해주는 것과 안 해주는 것

MCP는 에이전트에 도구의 이름·입력 schema·결과를 노출하는 연결 방식이다.
NAT는 MCP 도구를 소비하고, 도구나 workflow를 MCP 서버로 노출하는 기능을 제공한다.
REST API를 직접 호출하는 Python 함수가 충분하다면 MCP 서버를 별도로 만드는 것이 필수는 아니다.
근거: [NAT 프로토콜 지원](https://github.com/NVIDIA/NeMo-Agent-Toolkit#readme).

| 확인된 MCP 경로 | 가능한 일 | 주의할 경계 |
|---|---|---|
| Retriever MCP | `query`, `ingest_documents` | 서버가 읽을 수 있는 문서·경로 필요 |
| AI-Q MCP | `submit_query`, `poll_query`, `get_final_report` | 공개 서버 구현은 무인증·신뢰 경계 필요 |
| NemoClaw 문서 MCP | `searchDocs` 등 문서 탐색 | 에이전트 실행 도구가 아닌 문서 검색 |
| NemoClaw 관리형 MCP 통합 | 외부 MCP 서버 연결·운영 | 공급자 인증·네트워크 정책 필요 |

근거: [AI-Q MCP 설명](https://github.com/NVIDIA-AI-Blueprints/aiq#mcp-server), [NemoClaw 문서 스킬](https://github.com/NVIDIA/skills/blob/fd9f1466ff8a39178e488981e8b5118709392949/skills/nemoclaw-user-guide/SKILL.md), [NemoClaw 문서](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/home).

**분석:** “NVIDIA에 Slack·회사 DB·메일 스킬이 있다”는 것과 해당 계정에 연결되어 있다는 것은 다르다.
실제 외부 시스템에는 각 서비스의 API·인증·조직 권한이 필요하다.
이 조사를 위해 사용자의 외부 계정이나 업무 데이터에 연결하지 않았다.

## 평가와 통제: 역할이 다른 도구

| 제품 | 관찰·검증 대상 | 적합한 사용 |
|---|---|---|
| NAT evaluation/profiler | 에이전트 workflow 품질·시간·실행 | 도구 포함 전체 작업 비교 |
| `rag-eval` | 근거 검색·답변 품질 | 문서 질의 평가 |
| `rag-perf` | RAG 지연·처리량·오류 | 부하와 병목 비교 |
| NeMo Evaluator | 모델 endpoint·benchmark | 모델 품질 비교 |
| SkillEvaluator | 스킬 품질과 사용 시 행동 변화 | 자체 스킬 개발·품질 검사 |
| NeMo Guardrails | 대화·입력·출력·검색·실행 규칙 | 앱의 정책 적용 |
| OpenShell | 파일·네트워크·프로세스 경계 | 도구 실행 환경의 권한 제한 |

근거: [NAT 평가](https://docs.nvidia.com/nemo/agent-toolkit/latest/workflows/evaluate.html), [Evaluator](https://docs.nvidia.com/nemo/evaluator/latest/), [SkillEvaluator](https://github.com/NVIDIA/SkillEvaluator), [Guardrails](https://github.com/NVIDIA-NeMo/Guardrails).

Guardrails는 설정한 규칙을 애플리케이션에 적용하는 도구다.
입력·대화·검색·실행·출력의 다섯 경로를 다룰 수 있지만, 설정하지 않은 규칙이 자동 적용되지는 않는다.
프롬프트 공격이나 잘못된 결과를 완벽히 막는다는 보장은 아니다.

## 도구 인터페이스의 최소 설계 — 분석

각 도구에는 이름·설명·입력 schema·출력 schema·오류 형식·timeout·허용 부작용을 정의한다.
검색은 문서 ID·페이지·원문 근거, 최적화는 solver 상태·목적값·제약 위반, 파일 생성은 실제 경로를 반환하게 한다.
에이전트에는 도구 응답을 보지 않고 성공을 선언하지 못하도록 완료 기준을 둔다.
데모 로그는 비밀키나 전체 민감 문서 대신 도구명·요약 인자·상태·시간·산출물 식별자를 기록한다.
