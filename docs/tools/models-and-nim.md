# NVIDIA 모델과 NIM: 무엇을 호출할 수 있는가?

> 이전 기록: `nvidia/docs/10-nvidia-models-nim.md`에서 2026-09-24 이관. 아래 조사·작성 기준일을 유지하며 이번 이관에서 외부 사실이나 실행 결과를 재검증하지 않았습니다.

기준일: 2026-09-22. Build 카탈로그의 모델 제공 상태·API 제한은 변동 가능하다.

## Nemotron과 NIM의 차이

**Nemotron은 모델 계열**, **NIM은 모델을 서비스하는 추론 구성요소**다.
NVIDIA Build의 호스팅 엔드포인트를 호출할 수도 있고, 지원 환경에 NIM을 직접 배포할 수도 있다.
NIM 카탈로그에는 NVIDIA 외 공급자의 모델도 있다. [NIM 개요](https://docs.api.nvidia.com/nim/docs/overview), [Build 카탈로그](https://build.nvidia.com/explore/discover)

| 필요한 기능 | 모델/서비스 종류 | 에이전트에서의 역할 |
|---|---|---|
| 계획·도구 호출·설명 | Nemotron 언어/추론 모델 | 행동 선택, 인자 생성, 결과 해석 |
| 문서 검색 | embedding 모델 | 질의·문서를 벡터로 변환 |
| 검색 품질 보강 | reranking 모델 | 검색 후보의 관련성 재평가 |
| 이미지·영상 이해 | VLM, Cosmos 계열 | 시각적 내용 분석·장면 설명 |
| 문서 구조 추출 | OCR·layout·table 관련 모델 | 페이지·표·그림을 검색 가능하게 변환 |
| 음성 입력·출력 | ASR·TTS·NMT | 전사·합성·번역 |
| 내용 정책 검사 | content-safety 모델 | 입력·출력의 정책 위반 분류 |

이 목록은 기능 구분이며 모든 모델이 같은 API 형식·언어·라이선스·호스팅 옵션을 제공한다는 뜻은 아니다.
근거: [AI-Q 기본 모델 구성](https://github.com/NVIDIA-AI-Blueprints/aiq), [RAG 구성](https://github.com/NVIDIA-AI-Blueprints/rag), [Speech 지원표](https://docs.nvidia.com/nim/speech/latest/reference/support-matrix/asr.html).

## 조사 시점에 확인한 대표 모델

| 모델 ID/계열 | 확인된 용도 | 선택할 때 확인할 점 |
|---|---|---|
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 긴 작업·에이전트·tool use 지향 | 한국어 품질, 구조화 출력, API별 문맥 상한 |
| `nvidia/nemotron-3-ultra-550b-a55b` | 큰 추론·계획·코딩 모델 | API 지연·제한, 자체 호스팅 자원 |
| `nvidia/nemotron-3-embed-1b` | AI-Q의 기본 텍스트 임베딩 | 검색 데이터와 언어·차원·색인 호환 |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | AI-Q의 선택적 이미지/차트 추출 | 멀티모달 입력 형식·서비스 제공 상태 |
| Cosmos Reason 계열 | VSS의 영상 이해 구성 | 배포 버전·프로파일별 지원 모델 |

근거: [Lightning 모델 카드](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b/modelcard), [Ultra](https://build.nvidia.com/nvidia/nemotron-3-ultra-550b-a55b), [AI-Q](https://github.com/NVIDIA-AI-Blueprints/aiq), [VSS](https://build.nvidia.com/nvidia/video-search-and-summarization/blueprintcard).

## 한국어와 모델 크기에 대한 중요한 해석

Lightning 모델 카드는 30B 전체 파라미터, 3B 활성 파라미터, 최대 1M context를 안내한다.
명시된 지원 언어 목록에는 한국어가 없다. 이는 한국어 응답이 불가능하다는 뜻은 아니지만, 한국어 업무 정확도를 전제로 선택할 근거는 부족하다.
따라서 한국어 지시·고유명사·숫자·도구 인자·기권 사례를 실제로 평가해야 한다.
근거: [Lightning 모델 카드](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b/modelcard).

**분석:** MoE의 활성 파라미터 수를 모델 전체의 GPU 메모리 요구량으로 계산하면 안 된다.
30B 가중치를 단순 계산하면 BF16 약 60GB, 4bit 약 15GB이나 이는 가중치만의 거친 하한이다.
KV cache·양자화 부가정보·runtime·context·batch가 더 필요하고, 지원 GPU 커널·체크포인트도 맞아야 한다.
1M context라는 모델 능력 상한이 무료 API의 실제 요청 상한이나 단일 L40S의 실용 길이를 뜻하지도 않는다.

## API 경로와 자체 호스팅 경로

| 구분 | 호스팅 API | 자체 NIM |
|---|---|---|
| 실행 위치 | NVIDIA 호스팅 환경 | 보유 GPU 또는 임대한 서버 |
| 준비 | 계정·키·모델 엔드포인트 | 지원 GPU·OS·컨테이너·드라이버·모델 |
| 장점 — 분석 | 초기 구성과 모델 교체가 쉬움 | 실행 환경과 데이터 경로를 통제 |
| 병목 — 분석 | 네트워크, 호출 제한, 가용성 | 메모리, 설치, 로딩, 버전 호환 |
| 확인 사항 | 평가 서비스 조건·quota·입력 데이터 | 다운로드 권한·모델 및 NIM 조건 |

공식 FAQ는 개발자 프로그램의 프로토타이핑 접근과 운영용 AI Enterprise 조건을 구분한다.
호스팅 무료 체험을 무제한 운영 API로 가정하지 않는다. [공식 FAQ](https://docs.api.nvidia.com/nim/docs/product)

## 첫 검증에서 볼 것 — 분석

단순한 텍스트 응답 다음에 **실제 도구 호출→도구 결과 전달→최종 답변**이 성공하는지 확인한다.
JSON 인자 오류, 없는 도구 호출, 반복 호출, timeout, 응답 언어를 함께 기록한다.
모델의 benchmark 순위보다 사용할 작업의 완료율·지연·비용이 선택에 직접적인 근거가 된다.
