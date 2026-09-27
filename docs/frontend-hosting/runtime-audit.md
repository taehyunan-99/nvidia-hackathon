# 실행 경로와 설계 차이 점검

점검일: 2026-09-27. 기준 코드: `78019c7a5d64f11ace0ee56ff076d27f236d1f03`.
초기 S21 점검 뒤 사용자 요청으로 코드 수정과 세부 재점검·격리 이미지 검증을 수행했다. 1–6절은 기준 커밋의 최초 발견 기록이며, **현재 로컬 E2E 준비 상태는 10절, 이전 수정 기록은 7–9절**을 따른다. [파일별 점검표](runtime-files.md)를 함께 본다.

## 1. 점검 범위와 근거

Git 추적 파일 495개를 목록화하고 Python 126개 파일의 정적 import와 프런트 소스 22개 파일의 import를 추출했다. 여기에 CLI, 동적 로딩, Docker COPY, Compose 명령, CI, 데이터 파일 참조를 대조해 아래 실행 지도를 만들었다. 파일 전체 목록화와 모든 함수의 정확성·보안 검증은 구분한다. 개인 환경 파일의 값은 출력하지 않았다.

인계 기준의 변경 파일 28개는 저장된 SHA-256과 모두 일치했다. `1c15305 → a0f757e → 78019c7` 이력과 원격 main 일치, 깨끗한 작업 트리로 이전 작업의 정상 병합을 확인했다. 초기 점검은 `docs/runtime-audit`에서 문서만 작성했으며, 후속 사용자 요청으로 같은 브랜치에서 아래 결함도 수정했다. `docs/plan.md`, 최상위 README, 기존 로컬 자료와 실행 중 서비스는 보존했다.

개인 실행 근거는 같은 checkout의 `tmp/runtime-audit/`에 있다: `tracked-files.txt`, `inventory.py/json`, `probe.py/json`, `boundary_probe.py`, `boundary-probe.json`, `pytest.log`, `build.log`, `frontend-tests.log`, `contracts.log`. 아래 표에는 로컬 파일 없이도 확인할 수 있도록 재현 조건과 관찰값을 함께 적었다.

## 2. 실행 진입점과 산출물

| 진입점 | 실제 연결 | 모드·산출물·경계 |
|---|---|---|
| `frontend/index.html → src/main.tsx` | `AgentStart`/`PersistentInput → persistent-mock.ts → /api/config`, 세션·review·run API | Compose는 `VITE_PERSISTENT_SERVICE=1`, API base 빈 문자열. 이름이 mock인 클라이언트도 live를 처리하므로 삭제 대상 아님 |
| `service.operational:from_environment` | PostgreSQL migrations, 세션 소유권, 입력·업로드 저장, 실행 접수·결과/파일 조회 | `DATA_MODE=mock` 기본, `live` 허용. 서버 mode와 결과 mode를 프런트에서 대조. API가 분석하지 않음 |
| `python -m service.worker` | `claim → process_one → _mock_output` 또는 `request_for_job → run_process → finish_live` | 모드별 작업 점유, live는 DB advisory lock으로 동시 실행 1개. 30초 lease, 5초 단위 heartbeat. 만료·삭제 후 파일 정리 |
| live subprocess `python -m logic.run` | `flow → agent_session/nat_agent → structure_sources/structures → prediction_validation/analysis/contacts/surface_analysis → review_policy` | request/output JSON, progress JSONL, 구조·조회·호출 기록. 검증된 결과와 ready 파일만 DB·artifacts에 저장 |
| `LOGIC_AGENT_MODE=nat` | `nat_workflow.yml → nat_agent` 도구 등록 → `nat_model.PacedNIM` | NAT의 모델 선택·도구 호출. 실패하면 이미 끝난 작업을 보존하면서 `RuleDecider`로 재개. `runtime_skill`의 고정 Boltz 스킬은 프롬프트 입력이지 단독 모델 실행 아님 |
| `LOGIC_AGENT_MODE=rule` | `flow._run_candidate → Decider → NvidiaClient.chat`, 필요 시 Boltz | 고정 순서일 뿐 오프라인 모드가 아님. 키가 있으면 Nemotron·Boltz 호출 가능. NAT 실패 후의 `RuleDecider`와 구분 |
| `service.app:app` | `/api/review → flow`, preset·artifact API | 별도 동기식 개발 시연. 세션·DB·점유·만료 정리 없음. 기본 Vite 실행은 이 API를 사용하고 Compose는 사용하지 않음. 아직 실행 가능한 경로여서 무단 삭제 금지 |
| `ReviewOverview / PredictedStructure / molecular-viewer` | live의 실행별 artifact·해시·사슬·잔기, mock의 `StructurePreview` | mock의 공개 구조 예제는 검토 후보와 별도임을 표시. 실험 좌표도 계산 결과·결합력 검증과 구별 |
| `ReportView` | 동일 Result의 근거·의견·출처·artifact 링크 | 현재 구조 파일 다운로드만 실제 생성 경로와 연결. JSON·CSV 요구의 공백은 F03 참조 |
| Docker/Caddy/Compose | web 빌드 → `/api` reverse proxy → operational; 별도 worker와 DB/migrate | local은 loopback HTTP, server 구성은 loopback HTTPS 리허설. 공개 배포·이미지 내부 실호출 검증과 별개 |

### 런타임 의존 파일과 보존 대상

| 경로·코드 | 참조 근거 | 분류·처리 |
|---|---|---|
| `docs/topics/her2/assets/a02/metrics.py` | `logic/surface_analysis.py`의 `importlib.util.spec_from_file_location` | 실제 좌표 표면 계산 의존. 문서 assets라는 이유로 제거 금지; Bio.PDB·NumPy 필요 |
| `frontend/public/structures/*.cif`, `contacts.json` 및 검증 catalog | `structures.load_catalog`, `analysis._reference_epitope`, 공개 미리보기 | 실제 구조·서열·독립 접촉 대조 자료. API Docker에도 COPY됨 |
| `docs/frontend-hosting/contracts/service.schema.json` | `logic.contract`, 서비스 입력·진행·결과 검사 | 실제 계약 원본. 프런트 `scenario-file.ts`는 별도 제한적 표시 검사이며 서버 검증 대체 아님 |
| `logic/skills/boltz2-nim/*`, manifest, YAML | `runtime_skill`, `nat_agent`, `nat_workflow.yml` | 실제 실행의 스킬 신원·프롬프트·도구 등록. 사용되지 않는 프로젝트 작업 스킬과 혼동 금지 |
| `service/mock_scenarios.json` | `_mock_output`, 원본 일치 검사 | 실제 mock worker의 패키징된 fixture. 계산값을 실측으로 승격하지 않음 |
| `docs/frontend-hosting/fixtures/` | 입력 화면의 공개 입력, 만료 화면 기본값, TS 타입, 계약·mock 검사 | 공개 실제 입력과 합성 상태 fixture를 구분해 보존 |
| `logic/analysis.contact_measurement` | `logic/tests/test_contacts.py`의 사전 접촉값 대조 | 현재 제품 계산은 좌표 기반 `predicted_contact_measurement`를 공통 사용. 기존 함수는 회귀 대조용이므로 유지 |
| `logic/measure_agent.py`, `check_key.py` | 명시적 CLI; 전자는 tests의 입력 도우미를 import | 개발 평가·계정 진단 도구. 제품 API/worker의 호출 경로 없음. 실제 모델 호출 가능하므로 이번 점검에서 실행 안 함 |
| `docs/topics/her2/assets/a01,a02,a03,goldset,hackathon-evaluation/` | 자료 생성·독립 평가·연구 재현 명령 | runtime 의존인 metrics와 나머지 연구 자료 구분. 기본 pytest 밖 연구 검사는 별도이며 제거하지 않음 |
| `test/*.json` | 과거 UI 업로드 시나리오 자료 | 현재 입력 화면에는 업로드 경로 없음. 자료 자체는 유지하고 `test/README.md`의 자동 재생 안내를 고칠 후보 |
| `.agents/`, `.claude/`, `.codex/`, `.github/` | 명시 스킬·wrapper·개발 설정·CI | 개발 협업 경로. HER2 서버 실행 의존 아님. 이번에는 스킬 구현 감사·변경을 하지 않음 |
| `tmp/`, 개인 `.env`, node_modules/dist/venv | 로컬 증거·설정·생성물 | Git 밖 개인 자료, `.dockerignore`로 실행 이미지 유입 차단. 기존 파일 삭제 안 함 |

기준 커밋의 API 이미지는 service·logic·분석 assets 전체를 복사하여 개발 테스트와 연구 자료도 포함한다. 이는 제품에서 테스트를 실행한다는 증거가 아니다. 이미지 축소는 runtime 의존과 평가 도구 유지 여부를 별도로 확인한 뒤 판단한다. `uv sync --no-dev` 뒤 A-02 requirements 설치도 있으므로 최종 이미지 의존성은 lockfile만으로 검증됐다고 하지 않는다.

## 3. 재현된 문제와 최소 수정 범위

P1은 운영 준비를 막거나 거짓 완료를 만드는 문제, P2는 기능·검사·설정 누락, P3는 도달 불가 코드·안내 정리다. 알려진 미구현과 새로 재현한 결함을 구분했다.

| ID / 우선순위 | 관찰·직접 근거 | 다음 최소 수정과 통과 조건 |
|---|---|---|
| F01 / P1 / 재현 | `service.worker.cleanup_sessions`는 `shutil.rmtree(ignore_errors=True)` 뒤 `cleaned_at`과 `deleted`를 기록한다. 폐기용 DB에서 mock 실행·파일을 만들고 삭제 요청 후 rmtree 실패를 주입: 파일 존재=true, reported_cleaned=1, status=deleted, cleaned=true, 재시도=0 | worker와 수명 테스트에서 삭제 실패를 완료로 표시하지 않고 재시도 가능하게 남긴다. 한 세션의 실패가 다른 정리를 막지 않는지 확인. 실패→재시도→실제 제거를 검사 |
| F02 / P1 / 기존 미구현 | `operational.create_session/create_run`에는 사용자·전체 접수량/대기열 한도가 없고, `live.run_process`는 alive가 유지되는 동안 전체 경과시간 제한이 없다. 파일당 제한은 multipart 파싱 뒤 적용된다. NAT iteration·HTTP timeout·DB 동시 점유 제한은 전체 접수/실행 예산을 대신하지 않음 | 공개 사용 차단 유지. S22에서 제한 적용 지점과 회귀를 준비하되 사용자/운영 담당이 공개 상한·전체 시간 예산을 결정해야 함. S23은 승인된 값으로 초과·정상·재시작 검사; 임의 값으로 공개 가능 판정 금지 |
| F03 / P2 / 구현 누락 | PRD F09의 JSON·CSV 다운로드와 달리 `Flow.run`은 files=[]이고 artifact는 구조뿐이다. `ReportView`는 등록된 artifact만 링크하며 JSON/CSV 생성기가 없다. 서비스 JSON 파일 시험은 테스트가 직접 등록한 bytes로서 제품 보고서 생성 검사가 아님 | 같은 Result의 버전·실행 ID·출처·미확인/실패를 보존하는 보고 파일 생성/등록 및 다운로드 회귀. API 결과 조회를 파일 생성 완료로 세지 않음 |
| F04 / P2 / 재현 | `scripts/check_server_flow.py` create는 원본 합성 fixture target을 사용한다. 현재 `_check_input`에 같은 input 전달 시 HTTP 422, “HER2 표적 ID와 검증된 세포외 구간 서열이 필요합니다.”. `check_mock_flow.py`에는 이미 공개 target 교체가 있음 | 리허설 입력을 현행 공개 표적으로 맞추고 동일 입력을 API가 접수하는 검사 추가. 다음 서버 리허설에서 create→restart→verify 수행. 현재 실패는 입력 검사 재현이며 HTTPS 전체 재실행 결과가 아님 |
| F05 / P2 / 재현 | 호스트 `PDB_SEARCH_ENABLED=0`을 주고 `docker compose config --format json`을 확인해도 worker 환경에 이 항목 없음. `structure_sources.lookup` 기본은 1. 두 Compose 모두 누락 | 양쪽 worker에 검색 설정을 전달하고 예시/검사를 연결. 검색 disabled 유지 및 enabled의 명시적 대역 시험. API 키/모델 허용과 별개임을 유지 |
| F06 / P2 / 보관 공백 재현 | 삭제 후 접근은 401이지만 reviews 1행·runs 1행과 후보 서열이 DB에 남음. cleanup은 파일과 session 상태만 처리. 호스팅 요구의 DB 입력·결과 수명은 미결정 부분 포함 | 조회 차단과 물리적 정리를 분리. 삭제할 payload, 최소 tombstone, 로그·백업 보관 범위를 운영 담당/사용자가 결정한 뒤 FK 순서·복원 후 만료까지 검증. 파일만 지운 것을 모든 자료 삭제로 기록하지 않음 |
| F07 / P3 / 정적 도달성 확인 | `main.tsx`의 playing은 false로 시작해 모든 setter가 false. advance는 playing effect에서만 호출되므로 다중 시나리오 자동 재생이 도달 불가. `analysis.pending_measurements`는 정의 외 호출/설정 참조 없음 | 삭제된 업로드 UI에 딸린 main 재생 상태·timer를 좁게 정리하고 미사용 함수를 제거 후보로 삼음. `AgentActivity`의 별도 수동 기록 재생과 실제 polling·mock 결과는 보존. 테스트 자료 삭제는 포함하지 않음 |
| F08 / P2 / 시연 경로 표시 누락 | `ReportView.artifactUrl`은 비영속 live에서 predicted만 허용한다. `service.app.artifact`는 실행 폴더의 실험 구조도 제공하고 비교 화면은 이를 사용한다. 같은 동기 실행의 실험 구조가 보고 화면에서만 링크 없음으로 표시됨 | 시연 경로를 유지하는 동안 실제 ready 구조를 kind와 무관하게 같은 run artifact URL에 연결하고 experimental/predicted/미완성 각각 검사 |

F01과 F06은 구별된다. F01은 삭제 실패를 숨기는 확정 오류이고, F06은 정상 파일 삭제에도 DB 자료가 남는 수명 정책·구현 공백이다. 이번 재현은 모의 실행과 일시 디렉터리만 사용했으며 기존 세션·파일을 삭제하지 않았다.

## 4. 모의·실제 경계 판정

- mock worker는 합성 상태를 복제하고 ready 구조 파일을 만들지 않는다. mock 결과·공개 예제 미리보기의 표시도 분리되어 있다. 현재 확인한 경로에서 fixture를 실측 수치로 바꿔 live 결과에 삽입하는 연결은 발견하지 못했다.
- live는 실제 로직 실행을 뜻한다. 공개 실험 좌표 재사용, 실제 좌표 계산, 모델 예측, 모델 실패 후 규칙 재개는 서로 다른 사건이다. `Flow._explain`, activity actor·fallback, 항목별 review_policy가 이 구분을 유지한다. 모델 요청 대역으로 Decider를 검사한 결과 요청 시도 1회 후 규칙 복구였으며 외부 전송은 0회였다. `rule` 설정이나 `check_live_flow.py`의 “without model charges” 설명만으로 무과금 실행을 보장할 수 없다.
- 공개 PDB 번호/자동 검색은 외부 구조를 받은 뒤 전체 중쇄·경쇄·HER2 607잔기를 검증한다. 검색 해제는 번호 없는 자동 검색만 막고 명시 출처 조회까지 막는 설정은 아니다. 계산 불가 좌표·부분 점유율·미확인 당은 보류한다.
- 업로드 API는 파일 저장·파싱·무결성을 확인하고 LogicRequest에 전달하지만 분석 flow는 uploads를 소비하지 않는다. PRD의 후속 결정에 따라 현재 직접 입력 UI에서 숨긴 의도된 미지원이다. 임의로 분석을 연결하지 않으며 API 소비 안내는 이 경계를 유지해야 한다.
- `main.tsx`의 남은 labels.reviewable 문구는 현재 scenario.name 라벨에만 사용된다. 실제 의견 화면은 “해당 항목 검토 가능”을 사용하므로 이 문자열만으로 기존 의견 오표시를 주장하지 않는다.

## 5. 설계·문서 차이와 결정 주체

| 분류 | 권위·현재 상태 | 처리 |
|---|---|---|
| 구현 상태 설명 노후화 | PRD의 “현재 통과한 제품 검증은 없다”, topics/her2 및 topics 가이드의 “앱 빌드·테스트 명령은 아직 없다”, collaboration의 스택 미확정, worker의 mock-only docstring | 현행 상태 안내는 코드·이번 검사에 맞춰 S22에서 최소 수정. 작성 당시 조사·검증 기록은 날짜와 함께 보존 |
| 설계 선택과 구현 차이 | ADR-002는 React Router/결과 URL을 선택; package.json과 main은 React state·localStorage로 조회 | 현재 새로고침 복구와 결과별 URL 기능을 구분. Router 도입 또는 ADR 변경은 사용자/서비스 담당 결정 대상으로 남김; 과거 ADR 덮어쓰기 금지 |
| 명시 후속 결정 | PRD 후보 2–4·고정 607잔기·업로드 숨김·선택 출처·항목별 검토 | 이전 일반 입력 계획보다 후속 결정 우선. 일반 표적·파일 분석·효능 순위를 새 요구로 추가하지 않음 |
| 의도된 연구 한계 | 충돌·전체 접근성 미확인, 예측 정확도/독립 새 항체 효용 미입증 | 미구현 필수 동작과 과학적 근거 부족을 구분. 임의 threshold·점수로 보완하지 않음 |
| 읽기 전용 계획·과거 기록 | docs/plan.md의 초기 후보 2–3·초기 인계 제안, 날짜 있는 A/B·호스팅 조사 | 현행 PRD와 차이를 기록하되 plan 자체를 수정하지 않음. 과거 모델 성공/리허설을 이번 버전 성공으로 승격하지 않음 |
| 운영 계약 미확정 | PRD Q03·Q06, ADR-008, hosting-requirements의 보관·한도 | F02/F06에 결정 주체와 첫 검증 행동 명시. 공개 접수/전체 수명 준비가 끝난 것으로 표시하지 않음 |

## 6. 이번 검사와 다음 단계

격리 PostgreSQL 컨테이너 `her2-runtime-audit-db`의 새 DB에서 `NVIDIA_API_KEY='' NGC_API_KEY='' PDB_SEARCH_ENABLED=0 TEST_DATABASE_URL=<폐기용 DB> uv run --locked pytest -q`: **291 passed, 2 skipped**, 121.76초. 생략 2건은 `RUN_LIVE_NAT=1` 및 `RUN_LIVE_PERSISTED=1`에서만 실행하는 실제 모델 검사다. 경고 상세는 로그에 보존한다. 원래 사용자 DB와 기존 Compose 서비스는 사용하지 않았다.

`VITE_PERSISTENT_SERVICE=1 VITE_API_BASE='' npm --prefix frontend run build` 통과(500 kB 초과 청크 경고 유지), activity-state 검사 **8 passed**, 계약 검사 정상 **9개**·잘못된 변형 **9개 거부**. 삭제 실패/DB 잔존과 리허설 입력 오류는 기존 검사가 통과해도 별도 재현됐으므로 기준선 통과를 결함 없음으로 해석하지 않는다.

이번에는 NVIDIA 실호출, 공개 검색 재조회, 브라우저 전체 재검증, 최신 Docker 이미지 빌드·HTTPS·재시작·백업 복원, 연구 자산 전체 재생성을 수행하지 않았다. `.github/workflows/integration.yml`은 계약·서비스/로직·기본 프런트 빌드·Compose mock을 실행하지만 서버 HTTPS 복원과 실제 모델 완주를 보장하지 않는다. CI Python 3.12/Node 24와 이미지 Python 3.13/Node 25 차이도 유지된다.

초기 점검 뒤 아래 후속 수정과 재검증을 수행했다.

## 7. 후속 수정과 재점검 결과

| 항목 | 현재 상태 | 직접 확인 |
|---|---|---|
| F01 삭제 실패의 거짓 완료 | 수정 | 실패한 세션의 cleaned_at을 남기지 않고 다음 정리에서 재시도. 다른 세션은 정리 가능. 실패→재시도 회귀 통과 |
| F02 실행 제한 | 로컬 기준 구현, 공개 보호는 미완료 | 사용자 승인: 세션당 대기·진행 1건, 전체 10건, live 동시 1건, 실행 1200초. DB 잠금으로 동시 접수 경쟁 제어, 같은 접수 키 재시도 보존, 초과 429와 timeout 프로세스 종료 검사 |
| F03 JSON·CSV 보고 | 구현 | 소유 세션의 같은 DB Run/Result를 조회해 다운로드. JSON 전체 snapshot과 CSV의 상태·수치·사유·출처·원본 record_json 보존. 실제 좌표 계산을 거친 이미지 API 결과와 다운로드 일치 확인. CSV 수식 시작 문자는 비실행 처리 |
| F04 리허설 입력 | 수정 | 공개 HER2 target으로 교체. 최신 HTTPS 이미지의 mock create/verify 검사 |
| F05 검색 설정 | 수정 | 두 Compose의 worker에 PDB_SEARCH_ENABLED 전달. 실제 실행 컨테이너의 자동 검색 해제, config 검증 |
| F06 자료 수명 | 구현 | 사용자 위임에 따라 기존 30분 만료 후 파일·DB 입력·결과 삭제, 세션 tombstone만 유지. 복원 환경에서도 삭제 후 조회 차단과 실제 파일/DB 제거 확인. 운영 임시 결과의 정기 백업은 만들지 않고 검증 백업만 사용 |
| F07 미사용 코드·안내 | 정리 | 옛 시나리오 재생 state/timer/다음 기록 분기, pending_measurements, 미사용 Scenario import와 viewer options 제거. 수동 활동 재생·polling·모의 fixture·독립 대조 함수·연구 자료 보존. test/README와 현행 가이드 수정 |
| F08 실험 구조 다운로드 | 수정 | 동기 시연에서도 experimental/predicted ready 구조를 같은 실행 URL로 연결. 영속 경로는 기존 소유권 검사 유지 |
| F09 산출물 경로 검증 | 추가 발견·수정 | experimental이라는 분류만으로 폴더 밖 파일을 허용하던 조건 제거. 검증 catalog의 정확한 파일·해시만 fallback 허용. 경로 이탈·symlink·중복 ID 검사 |
| F10 실모델 검사 신뢰성 | 추가 발견·수정 | 영속 실모델 검사에 live marker가 빠져 전역 fixture가 키를 제거하던 문제 수정. NAT 실검사도 규칙 복구·agent 오류가 없는 실제 도구 실행을 요구. 이번에는 두 실검사 모두 의도적으로 생략 |
| F11 근거 선택과 3D | 추가 발견·수정 | 비교 화면이 선택 근거를 viewer에 전달하지 않아 접촉 잔기에 머물렀다. 선택 근거의 관측 잔기를 전달하고 근거 변경 시 강조 갱신; 미확인 근거는 이전 강조 해제. 실제 브라우저로 확인 |
| F12 잘못된 모드의 암묵 실행 | 추가 발견·수정 | LOGIC_AGENT_MODE 오타가 rule로 실행되던 경로를 명시 오류로 변경. rule의 모델 호출 가능성을 실행 안내에 명시 |
| 실행 이미지·CI | 정리 | API는 동적 metrics·스키마·실제 구조·고정 스킬만 필요한 자료로 포함하고 제품 테스트·benchmark·과거 연구 결과 제외. uv.lock 뒤 별도 의존성 덮어설치 제거. CI와 이미지 Python 3.13/Node 25 정합 및 활동 상태 검사 추가 |

별도 동기 시연 API와 mock 모드는 사용 경로·검증 용도가 있으므로 유지한다. 이름만 보고 삭제하지 않았으며 제품 코드가 테스트 입력 생성기를 import하는 경로는 발견하지 못했다. 개발용 measure_agent는 테스트 도우미를 참조하지만 API 이미지에서 제외했다. 후보 이름·고정 PDB 번호로 임의 과학적 판정을 생성하는 기능은 추가하지 않았다.

## 8. 후속 실행 근거와 재현 범위

- 제품 전체: 새 폐기용 PostgreSQL에서 **300 passed, 2 skipped**. 실제 모델 두 검사는 별도 승인 없이 실행하지 않았고, 기본 테스트의 NAT 도구 응답 대역은 실모델 성능 증거가 아니다.
- 프런트: 타입·빌드, `--noUnusedLocals --noUnusedParameters`, 활동 상태 8건, 계약 정상 9개/잘못된 변형 9개 통과. 큰 viewer 청크 경고는 남는다.
- 이미지: 현재 소스로 API/web을 빌드. 소스 마운트 없이 고정 스킬·NAT·동적 계산 import 통과, 테스트·benchmark 파일 미포함 확인. `DATA_MODE=live`, `LOGIC_AGENT_MODE=rule`, 두 NVIDIA 키 없음, 자동 검색 0에서 공개 실험 좌표를 실제 계산하고 진행·저장·구조 해시·다른 세션 접근 차단을 확인했다. live는 NVIDIA 호출 성공과 동의어가 아니다.
- 브라우저: 이미지에서 새 입력→진행→비교→선택 근거 강조→미확인 근거 강조 해제→보고서 JSON 다운로드 확인, 페이지 오류 0. mock도 새 실행 후 공개 미리보기와 결과의 분리, 모의 보고 표시, 실측 근거 0을 검사했다. 전체 브라우저·접근성·장시간 성능 검증을 대신하지 않는다.
- 운영: loopback HTTPS를 검사 전용 CA로 검증하고, 브라우저는 해당 임시 leaf 공개키만 고정해 사용했다. OS 신뢰 저장소를 바꾸지 않았다. 서비스 정지 뒤 일관된 DB/파일 백업을 다른 프로젝트의 새 볼륨에 복원해 동일 상태·결과·파일·보고서를 확인하고, 삭제 후 자료 제거를 검사했다. 공개 DNS/AWS/공인 인증서는 실행하지 않았다.
- 연구 별도 검사: A-01 **9/10**, A-02 **17/18**, A-03 **13/15**. 실패는 A-01 재생성 환경 메타데이터, A-02 floating-point 마지막 자리의 byte 불일치, A-03 이전 service.schema.json 해시 및 Python 버전 메타데이터 차이다. 재생성 실패를 숨기거나 현재 값으로 과거 정답을 덮어쓰지 않았다. 독립 기하·자료 대응 검사는 통과했지만 연구 byte 재현성 전체 통과는 아니다. 검사 스크립트가 만든 tracked generated 변경은 개인 증거에 보존하고 실행 전 원본으로 복원했다.

후속 근거는 `tmp/runtime-audit/final-tests.log`, `final-build.log`, `final-frontend-tests.log`, `image-imports.log`, `image-live-flow.log`, `browser-summary.json`, `browser-*.png`, `operations.log`, `restore-verify.log`, `cleanup-image.log`, `mock-server-flow.log`, `mock-browser-summary.json`, `research-output/`에 있다. 실행별 cookie·env·검증 백업은 개인 파일이며 Git에 포함하지 않는다.

## 9. PRD 대비 현재 상태와 공개 사용 전 잔여 조건

| 요구 | 연결·확인된 동작 | 남은 범위 |
|---|---|---|
| F01/F02 입력·자료 대응 | HER2 607잔기, 후보 2–4, 서열·출처·사슬 검증; 변이와 부모 구조 구별 | UI에서 숨긴 업로드 구조 분석은 의도된 미지원. API 저장만으로 사용했다고 하지 않음 |
| F03 필요한 분석 선택 | 로컬/명시 출처/제한 검색, NAT 도구 관문, 규칙 복구와 실제 좌표 계산 | 모델이 교차 확인 예측을 선택할 수 있으므로 공개 입력 자체가 무호출 보장은 아님. 최신 실모델 완주·비용·호출 시간 미검증 |
| F04/F10 진행·복구·부분 결과 | 저장된 이벤트·후보 상태·소유권·중단/timeout, 새로고침과 격리 복원 | 최신 호스트 장애·외부 요청 취소/결과 조회 및 장시간 검증 미완료 |
| F05/F06 구조·조건 비교 | 공통 접촉·표면·관측 NAG 비교, 미지원 조건은 사유와 null | 충돌·전체 접근성·자세 일관성·새 항체 예측 정확도를 구현/검증 완료로 확대하지 않음 |
| F07/F08/F09 비교·의견·보고 | 선택 근거와 관측 잔기 연결, 항목별 제한된 의견, 같은 snapshot 내보내기 | 과학적 순위·효능 판단 제외. 전체 키보드/저해상도/3D 성능 검증은 추가 필요 |
| ADR-002 결과 URL | 현재 React state/localStorage로 같은 세션의 실행을 복구 | React Router·실행별 URL 미구현. 같은 세션 데모 복구와 결과 URL 요구를 구분해 남김; ADR를 임의 변경하지 않음 |
| 공개 운영 보호 | 실행 동시성·대기열·시간·파일당 제한, 만료와 자료 삭제 | 익명 세션 신규 발급·요청 빈도·총 저장량·multipart 수신 전 제한은 미완료. 공개 연결 전에 전체 요청 예산과 대표 부하 검증 필요 |
| 배포 준비 | 현재 이미지의 격리 실제 좌표 계산·모의 모드·HTTPS·복원·삭제 확인 | 실제 AWS·공인 HTTPS·현행 NVIDIA 실호출·과학적 독립 평가 미실행. 공개 서비스 준비 완료로 승인하지 않음 |

다음 작업은 위 잔여 조건을 기능·운영 계약별로 닫는 것이다. 우선 공개 요청/저장 자원 제한을 구현·부하 검증하고, 실제 모델 검사는 별도 허용된 호출 범위에서 수행한다. 역사적 연구 재현성은 환경을 고정한 재생성 또는 수치·환경을 분리한 검증 방식의 검토가 필요하며 허용 오차를 임의로 늘려 통과시키지 않는다.

## 10. 로컬 E2E 전 잔여 문제 해결

사용자는 배포를 보류하고, 알려진 코드 문제 해결 → 반복 점검 → 사용자 로컬 실제 E2E → 이후 배포 판단 순서를 지정했다. 아래는 9절 잔여 항목의 후속 상태다.

| 이전 잔여 항목 | 적용한 해결 | 검증 경계 |
|---|---|---|
| 반복 요청·세션 대량 생성 | PostgreSQL minute counter로 변경 요청 빈도 제한, 세션 생성/입력 수 제한과 경쟁 잠금 | API 인스턴스 간 원자적 카운터·동시 요청 검사. 로컬 기본값은 변경 요청 120/분, 활성 세션 100, 입력 10/세션 |
| multipart 수신량·시간 | 파싱 전 Content-Length와 실제 chunk 누적 크기 검사, 30초 전체 수신 제한, 프로세스당 한 본문 수신 | 느린 수신과 계속 준비된 chunk 모두 시간 제한을 우회하지 못함. 21 MiB 초과 413, 수신 중 경쟁 429, 시간 초과 408 |
| 총 저장량 | DB 크기와 서비스 파일 합계 1 GiB 경계에서 접수/점유 거부, 실행 중 주기적 확인 후 초과 작업 종료 | 파일당 제한과 별개. OS hard quota가 아닌 경계값이며 쓰기 중 순간 초과가 가능함. 현재 단일 호스트 로컬 구성을 대상으로 함 |
| 실행별 주소 | `?run=`으로 기존 단일 화면의 실행 선택 연결, 새로고침·새 탭·history navigation 지원 | 새 탭·뒤로/앞으로·새로고침 통과. 원래 세션 없이 열면 거부, 잘못된/없는 주소도 다른 결과로 대체하지 않음. ADR-009에 기술 선택 기록 |
| 만료 화면의 합성 입력 | 실제 입력을 조회하지 못했을 때 fixture를 기본값으로 넣던 코드를 제거 | 만료를 새 검토 안내로 처리하며 후보·결과를 만들어 보여주지 않음. 프런트 fixture는 타입/명시적 mock 검사용으로 유지 |
| 연구 재현성 4건 | 현재 환경의 결과를 임시 폴더에서 생성한 뒤 독립 기하/원자료 기대값·현재 환경 byte 재생성을 검사. 과거 산출물은 원본 해시 검사로 분리 | 과거 파일을 갱신하지 않고, 수치 허용 오차도 변경하지 않음. A-01/A-02/A-03 기존 43건 및 추가 과거 산출물 해시 검사 2건 통과. 이전 환경과의 byte 동일성을 주장하지 않음 |
| 실제 모델·AWS | 사용자 직접 E2E와 그 이후 배포 판단 단계로 분리 | 이번 수정 검증은 NVIDIA 키 없이 공개 구조의 실제 좌표 계산을 수행. 실모델·새 항체 정확도·공개 배포 성공으로 표현하지 않음 |

사용자 실행 절차와 제한 설정·실제/모의 판정은 [local-e2e.md](local-e2e.md)에 정리했다. DB migration 005가 필요하며 Compose의 migration 서비스가 적용한다. 사용자 기존 DB/볼륨에 직접 검사를 실행하지 않았다.

새 검증 근거는 `tmp/local-readiness/`의 `product-tests.log`, `final-product-tests.log`, `deadline-tests.log`, `frontend-tests.log`, `a01.json`, `a02.json`, `a03.json`, `archive-a02.log`, `archive-a03.log`, `url-e2e.json`, `recreated-check.log`에 남긴다. 이전 실패 로그는 삭제하지 않는다. 현재 검사에서 재현된 수정 대상과 미실행 외부 모델 평가를 구분하며, 모든 가능한 결함이 없다는 보증은 하지 않는다.

최종 로컬 확인: 제품 전체 **305 passed / 실모델 2 skipped**, 추가 수신 경계 **2 passed**, 프런트 상태·주소 **10 passed**, 연구 기존 43건+과거 산출물 해시 2건 **45 passed**, 평가 도구 **9 passed**. 수신 기한의 연속 chunk 우회 보완 후 경계 검사와 최신 이미지의 413 응답을 다시 확인했다. 주소 E2E는 새로고침·새 탭·뒤로/앞으로·타 세션·잘못된/없는 주소를 통과했다. 과거 생성 파일과 읽기 전용 plan·최상위 README는 변경하지 않았다. 연구 검사를 CI에도 추가했으나 원격 CI 실행 성공은 주장하지 않는다.

## 2026-09-27 최근 변경 후 점검

이번 범위는 세 공개 입력의 접수·분석·저장 연결과 최근 카드·다중 후보·Bio-3 명칭 변경의 잔재다. 기존 두 실제 모델 실행은 보존하고 외부 모델을 다시 호출하지 않았다.

| 재현된 문제 | 수정과 확인 |
|---|---|
| 저장 실행 조회의 첫 응답이 늦으면 사용자가 연 직접 입력을 진행 화면으로 강제 전환 | 저장 실행 여부로 초기 화면만 결정하고 조회 응답이 화면 선택을 바꾸지 않게 수정. 4초 지연 모의 API로 수정 전 전환과 수정 후 입력 유지·저장 결과 복원·보고 이동을 확인 |
| 미실행·미확인·실패 계산에도 ‘구조에서 계산한 값’ 표시 | 측정 상태에 따라 ‘계산값 없음’으로 구분. 측정된 0과 모델 제공 신뢰도는 각각 보존·구분. 실제 React 보고서 렌더링 회귀 통과. 후보 요약도 ‘실행 보류·실패’로 범위 명시 |
| 예측 자세 근거가 구현되지 않은 화면 정렬을 약속 | 표적 정렬은 계산 과정이며 화면은 개별 구조 표시임을 명시. 원본·정렬 메타데이터·RMSD 계산은 유지. 기존 저장 보고서 원문은 수정하지 않음 |
| 실제 응답 오류를 삭제된 ‘모의 JSON 업로드’ 오류로 안내, 연결 확인 중 모의 실행으로 표기 | 검토 데이터 형식 오류로 통일하고 모드 확인 전 연결 대기를 표시 |
| README·개요·화면 문서의 기존 두 실험 후보, JSON 업로드·2–3개 상한·미연결 설명 | 세 카드와 예측 기본값, 직접 입력 2–4개, 현재 영속 연결 반영. 초기 설계·연구 기록은 당시 내용으로 구분하고 과학적 표적명·원자료·NVIDIA 원본 스킬 보존 |

검증 결과:

- 별도 폐기용 PostgreSQL에서 **제품 330건 통과, 실제 호출 opt-in 2건 생략**. 프런트 **12건 통과**, 타입·정적 빌드와 API/web Docker 이미지, 스키마 정상 9개·오류 변형 9개 및 문서 상대 링크·공백 검사 통과.
- 새 영속 회귀 3건은 공개 입력·출처 대응·분석·worker 저장 경로를 사용하고 예측 전송만 합성 좌표로 대체한다. example_id·후보 ID·구조 수·Fab37 보류, JSON/CSV·재접속·파일 크기/해시·타 세션 404를 확인했다. 새 NVIDIA 성공으로 집계하지 않는다.
- 이전 실제 Boltz 좌표 두 개를 재사용한 재계산에서 실험/예측/보류 세 흐름 모두 종료하고 측정 실패가 없었다. 6BHZ 후보와 WT의 기존 값·상태가 수치 오차 범위 내에서 일치하고 관측 당·unknown 접근성·Fab37 보류를 유지했다. 새 독립 예측이나 정확도 검증이 아니다.
- 브라우저 모의 접수에서 세 카드의 전송 JSON이 배포 fixture와 각각 동일했다. 직접 입력 네 후보의 ID·이름·고정 표적 전달도 확인했다. 모델 호출 없이 전송 선택 오류를 점검한 것이다.

개인 근거는 `tmp/post-update-audit/`의 `baseline-tests.log`, `final-tests.log`, `final-frontend-tests.log`, `scenario-persistence.log`, `replay/summary.json`, `ui-submissions.json`, 이미지 빌드·반영 로그다. 사용 중 분석이 없음을 확인한 뒤 기존 DB·파일을 보존하고 검증 이미지를 로컬 사이트에 반영했다. 이번 추가 NVIDIA 호출은 **0건**이다. 이전 사용량 24/60·2/4를 새 사용량으로 집계하지 않으며, 공개 배포·부하 성능·새 항체 일반 정확도와 모든 브라우저 조합의 완전 검증을 주장하지 않는다.
