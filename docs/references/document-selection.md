# 문서 선별·이관 기록

정리일: 2026-09-24. 원본 위치: 기존 `nvidia/docs/`. 원본 파일은 수정·삭제하지 않았다.
이관은 현재 작업 파일을 기준으로 하며 기존 저장소의 미커밋 문서도 포함했다.
보존 대상은 대회 진행 자료와 HER2 설계 관련 내용이다. 현재 진행 주제와 구현 범위는 [프로젝트 개요](../topics/her2/overview.md)를 기준으로 한다.

## 이관 또는 선별 편집

| 원본 파일 | 처리 | 새 위치 | 이유 |
|---|---|---|---|
| `01-hackathon-requirements.md` | 이관 | [hackathon/requirements.md](../hackathon/requirements.md) | 대회 조건 |
| `02-stack-map.md` | 이관 | [tools/stack-overview.md](../tools/stack-overview.md) | 구성요소 역할 |
| `03-nvidia-github-skills.md` | 선별 편집 | [tools/nvidia-skills-guide.md](../tools/nvidia-skills-guide.md) | 스킬 사용 기준만 유지 |
| `09-nvidia-agents.md` | 이관 | [tools/agent-frameworks.md](../tools/agent-frameworks.md) | NAT·NemoClaw·OpenShell |
| `10-nvidia-models-nim.md` | 이관 | [tools/models-and-nim.md](../tools/models-and-nim.md) | 추론 경로와 검증 조건 |
| `11-nvidia-tools-mcp.md` | 이관 | [tools/tools-and-mcp.md](../tools/tools-and-mcp.md) | 도구 연결·평가 |
| `13-runtime-cost-constraints.md` | 이관 | [tools/runtime-and-costs.md](../tools/runtime-and-costs.md) | Windows·API·GPU·비용 |
| `15-demo-readiness.md` | 이관 | [hackathon/demo-readiness.md](../hackathon/demo-readiness.md) | 검증과 데모 준비 |
| `16-sources-method.md` | 선별 편집 | [references/sources-and-method.md](../references/sources-and-method.md) | 남긴 문서의 출처·검증 범위 |
| `18-bionemo-molecule-protein-skills-tools.md` | 선별 편집 | [tools/her2-toolkit.md](../tools/her2-toolkit.md) | 사용자 확인: HER2 관련 도구만 발췌 |
| `22-nemoclaw-dli-course-notes.md` | 이관 | [hackathon/nemoclaw-course-notes.md](../hackathon/nemoclaw-course-notes.md) | 대회 안내 교육 참고 |
| `23-application-form-snapshot.md` | 이관 | [hackathon/application-form.md](../hackathon/application-form.md) | 제출 필드·미확인 조건 |
| `24-her2-antibody-agent-design.md` | 이관 | [topics/her2/agent-design.md](../topics/her2/agent-design.md) | 현재 진행하는 프로젝트의 원문 설계 |

## 제외

| 원본 파일 | 이유 |
|---|---|
| `04-skills-research-rag.md` | AI-Q·RAG는 현재 HER2 설계의 직접 실행 경로가 아님 |
| `05-skills-data-optimization.md` | 데이터 처리·수리 최적화 일반 조사 |
| `06-skills-vision-speech.md` | 영상·음성 주제 도구 조사 |
| `07-skills-physical-science.md` | 로봇·기상 등 다른 분야 조사 |
| `08-skills-training-infrastructure.md` | 추가 학습·인프라 전반 조사 |
| `12-nvidia-blueprints.md` | 범용 Blueprint 비교; 현재 설계 구현 범위와 다름 |
| `14-capability-matrix.md` | 여러 주제 후보의 구현 가능성 비교 |
| `17-agent-orchestration-workflow.md` | 사용자 확인: 후보 발굴·AI 평가 회의 논의안 제외 |
| `19-bionemo-hackathon-topic-research.md` | 25개 주제 후보 회의 자료 |
| `20-bionemo-topic-evidence.md` | 여러 주제의 근거 목록 |
| `21-bionemo-topic-scenarios-explained.md` | 25개 주제 시나리오 |
| `24-her2-antibody-agent-design.pdf` | Markdown 원문과 중복되는 파생 PDF |
| `README.md` | 별도 목차 대신 docs/AGENTS.md의 영역 지도로 안내 |
| `catalog/README.md`, `catalog/skills-01.md`~`skills-05.md` | 전체 366개 스킬 색인; 기존 자료에서 유지 |

기존 `output/` 발표자료와 임시 생성 폴더는 이번 docs 선별 범위에 포함하지 않았다.
루트 README.md는 요청대로 빈 파일이다. 기본 규칙·설정·영역 가이드는 이 저장소용으로 새로 작성했다.
이관 문서의 내부 상대 링크만 새 경로로 바꾸고, 조사일·외부 출처·미검증 상태를 유지했다.
