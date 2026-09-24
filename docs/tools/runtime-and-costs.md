# 실행 환경·비용·자원 제약

> 이전 기록: `nvidia/docs/13-runtime-cost-constraints.md`에서 2026-09-24 이관. 아래 조사·작성 기준일을 유지하며 이번 이관에서 외부 사실이나 실행 결과를 재검증하지 않았습니다.

기준일: 2026-09-22. 아래 수치는 출처의 해당 구성 기준이며 실측 성능은 아니다.

## 실행 경로 비교

| 경로 | 로컬 GPU | 준비할 것 | 현실적인 출발 범위 — 분석 |
|---|---|---|---|
| NVIDIA 호스팅 모델 API | 불필요 | 계정·키·네트워크·도구 코드 | 텍스트·검색·문서 에이전트 |
| PC에서 원격 GPU 서버 호출 | 불필요 | 원격 서버·모델·접속 | 계산·비전 도구를 서비스로 연결 |
| Brev L40S 1대 | 서버에 48GB | GPU VM·컨테이너·저장공간 | 지원 소형 모델·선택적 GPU 도구 |
| DGX Spark | 통합 메모리 128GB | ARM64 지원 소프트웨어·모델 | 지원되는 로컬 추론·시연 |
| 여러 GPU 전체 Blueprint | 여러 대 가능 | 배포별 support matrix | 전체 자체 호스팅·고부하 처리 |

근거: [Build](https://build.nvidia.com/explore/discover), [L40S](https://www.nvidia.com/en-us/data-center/l40s/), [DGX Spark 하드웨어](https://docs.nvidia.com/dgx/dgx-spark/hardware.html).

L40S의 48GB는 GPU 메모리이고 Spark의 128GB는 CPU/GPU가 공유하는 시스템 메모리다.
단순 용량비가 처리 속도비를 뜻하지 않는다. Spark는 ARM64 호환 컨테이너·패키지도 확인해야 한다.
**DGX Spark가 대회 소개에 등장한다고 참가자에게 모두 지급되는 것은 아니다.** 공개 혜택에서 확인한 지급 대상은 우승 1팀이다.

## 대회 자원과 개인 준비 자원

본선 10팀 혜택 이미지에 팀당 최대 USD 1,000 Brev 크레딧과 L40S 1대 구성이 표시되어 있다.
예선 이용 가능 여부, 사용 기간, 저장소 비용 포함 여부, 초과 비용 처리, VM 사양은 미확인이다.
근거: [본선 혜택 원문](https://cdn.day1company.io/prod/uploads/202609/132319-277/frame-2147239728.webp).

## Windows 개발 시 확인한 조건

| 구성 | 공식 문서의 조건 | 의미 |
|---|---|---|
| 원격 모델 API client | 서버가 추론 담당 | GPU 없이 앱 코드 작성 가능 |
| NemoClaw | WSL2 준비 경로 제공 | native PowerShell 설치와 구분 |
| OpenShell | Windows WSL2 experimental | 릴리스·기능을 고정해 검증 |
| NAT | Python 3.11~3.13 | PC의 기본 Python과 별도 환경이 필요할 수 있음 |
| Speech NIM | 모델별 WSL2 지원, TTS는 미지원 안내 | Linux GPU 서버나 API 경로 검토 |

근거: [NemoClaw prerequisites](https://docs.nvidia.com/nemoclaw/latest/user-guide/openclaw/get-started/prerequisites), [OpenShell](https://github.com/NVIDIA/OpenShell), [NAT](https://github.com/NVIDIA/NeMo-Agent-Toolkit), [TTS](https://docs.nvidia.com/nim/speech/latest/reference/support-matrix/tts.html).

NemoClaw 안내의 host 최소 조건은 4 vCPU, RAM 8GB, 여유 디스크 20GB이며 권장은 RAM 16GB·디스크 40GB다.
이는 **sandbox 실행 host** 조건이다. 로컬 LLM 실행용 메모리까지 충족한다는 뜻은 아니다.

## 전체 Blueprint를 그대로 설치할 때

RAG 지원표는 기본 자체 호스팅 Docker 구성에 3×H100/B200/RTX PRO 6000 등의 예시와 200GB 디스크 요구를 제시한다.
반면 Lite Mode는 GPU 없이 원격 API를 사용한다. 같은 “RAG”라도 자원 크기가 크게 다르다.
근거: [RAG 지원표](https://github.com/NVIDIA-AI-Blueprints/rag/blob/main/docs/support-matrix.md).

VSS Build 카드에는 검증된 전체 로컬 구성으로 4×L40/L40S 등의 예시가 있다.
최신 스킬의 base 참조에는 원격 추론·단일 GPU 혼합 등 다른 경로가 있다.
따라서 버전·프로파일·모델·동시 서비스 수를 맞추지 않고 “L40S 몇 대면 된다”로 결론 내리지 않는다.
근거: [VSS 카드](https://build.nvidia.com/nvidia/video-search-and-summarization/blueprintcard), [base 참조](https://github.com/NVIDIA/skills/blob/fd9f1466ff8a39178e488981e8b5118709392949/skills/vss-deploy-profile/references/base.md).

## 비용 구조 — 분석용 산식

- GPU 환경: `VM 시간당 요금 × 실제 켠 시간 + 저장소 + 전송 + 별도 API 비용`.
- 에이전트 API: `작업 수 × 작업당 모델 호출 수 × 평균 입력/출력 사용량`.
- RAG: 초기 문서 추출·embedding 비용과 반복 질의 비용을 구분한다.
- 영상: 영상 길이·샘플링 빈도·모델 호출·동시 스트림·저장 기간이 비용을 좌우한다.
- 검색 공급자·지도 API 등의 비용은 NVIDIA 크레딧으로 충당된다고 가정하지 않는다.
- 이번 조사에서는 확정되지 않은 Brev 인스턴스 가격이나 계정별 quota로 실행 가능 시간을 계산하지 않았다.

공식 NIM FAQ는 개발·시험 접근과 production 라이선스를 구분한다.
모델 라이선스, NIM 사용 조건, 호스팅 API 조건, 클라우드 비용은 각각 확인해야 한다. [공식 FAQ](https://docs.api.nvidia.com/nim/docs/product)
