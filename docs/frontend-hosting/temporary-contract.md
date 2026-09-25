# 서비스 개발용 임시 입출력 규격 v0.1.0

작성일: 2026-09-25. **사용자 요청으로 먼저 정한 서비스 개발 기준**이며, 로직 담당이 구현한 인터페이스나 과학적 판정 기준이 아니다. 이 규격으로 화면·서비스 API·worker 운영·Docker 작업을 시작하고, 실제 로직 결과는 adapter에서 이 규격으로 변환한다.

## 1. 원본과 변경 경계

| 파일 | 역할 |
|---|---|
| [service.schema.json](contracts/service.schema.json) | 입력·실행·결과·오류·세션의 필드·타입·enum·nullable 정의 원본 |
| [scenarios.json](fixtures/scenarios.json) | 합성 입력과 대기·진행·완료·보류·부분 실패·실패·중단·만료·입력 오류의 화면 개발용 예시 |
| [validate-contract.py](contracts/validate-contract.py) | 스키마·예시·ID 참조·상태 의미와 잘못된 데이터 거부 확인 |

필드는 snake_case, 식별자는 의미를 파싱하지 않는 문자열, 시각은 UTC RFC 3339, 버전은 `schema_version: "0.1.0"`으로 둔다. 객체의 정의된 필드는 모두 필수이며 값이 없으면 스키마에 허용한 `null` 또는 빈 배열을 사용한다. 필드 생략과 미확인을 혼용하지 않는다.

`data_mode`는 `mock` 또는 `live`다. **서버 실행 설정이 결정**하며 브라우저가 보내는 분석 모드로 사용하지 않는다. 모의 화면·다운로드에는 항상 모의 데이터 표시를 유지하고, live worker에 fixtures를 전달하지 않는다. 합성 입력의 짧은 서열은 실제 항체·HER2가 아니며 형식 연동 검사에만 사용한다.

JSON Schema의 `$defs`에서 각 자료형을 참조한다. 예를 들어 입력 검증은 `#/$defs/ReviewInput`, 결과 검증은 `#/$defs/Result`를 사용한다. 문서 표보다 스키마를 필드 정의 원본으로 삼고 향후 프런트 타입·FastAPI 모델은 이 원본과 대조한다.

## 2. 임시 입력 계약

`ReviewInput`은 `schema_version`, `example_id`, `public_data_confirmed`, `target`, `candidates`, `uploads`로 구성한다.

| 필드 | 임시 의미 |
|---|---|
| `example_id` | 예제 선택이면 예제 ID, 직접 입력이면 null. 예제 선택도 같은 입력 규격으로 풀어 새 실행을 접수 |
| `public_data_confirmed` | true여야 접수. 공개 자료 사용 확인이며 자료 공개 여부를 자동 판별한 결과는 아님 |
| `target` | HER2 식별자 또는 FASTA와 분석 구간·sources. 둘 중 적어도 하나 필요, 둘 다 있으면 로직이 일치 여부 확인 |
| `candidates` | 2–3개. 중복 없는 candidate_id, 표시 이름, 항체 형식, 중쇄·경쇄 FASTA, 각 분석 구간과 sources |
| `analysis_range` | 입력 서열 기준 1부터 시작하는 양끝 포함 start/end 또는 null. 구조 잔기 번호와 별개이며 null은 미정이지 전체 분석 허가가 아님 |
| `uploads` | 선택적인 파일 manifest. upload_key·원본 이름·pdb/mmcif 형식·후보·complex/context 역할·출처 |

`POST /api/reviews`는 multipart로 `metadata`에 ReviewInput JSON 문자열을, 각 파일은 manifest의 `upload_key`와 같은 part 이름으로 보낸다. `metadata`는 예약어이며 파일 key는 중복될 수 없다. 선택 자료가 없으면 파일 part를 보내지 않는다. 입력 manifest와 실제 파일 part는 정확히 대응해야 한다.

서버가 파일 형식·파싱·크기와 후보 대응을 다시 확인하고 실제 저장 위치·해시를 부여한다. 클라이언트의 파일명은 서버 경로로 쓰지 않는다. 허용 크기·서열 길이·분석 구간·항체 형식의 과학적 제약은 실제 입력 확인 후 설정하며 이 임시 스키마로 생물학적 유효성을 보장하지 않는다.

## 3. 임시 HTTP 경계

다음은 앞으로 구현할 경로이며 현재 동작하는 서버가 아니다. 성공 JSON은 표의 `$defs` 자료형과 일치시키고, 오류는 공통 `ApiError`로 반환한다.

| 메서드·경로 | 요청 | 정상 응답·의미 |
|---|---|---|
| POST `/api/session` | 본문 없음 | 201 Session. 임시 세션 발급 |
| POST `/api/session/heartbeat` | 본문 없음 | 200 Session. 유효한 세션의 expires_at 갱신 |
| DELETE `/api/session` | 본문 없음 | 202 Session. 접근 종료·삭제 요청 접수이며 물리적 삭제 완료가 아님 |
| POST `/api/reviews` | 위 multipart | 201 ReviewAccepted. 입력 접수만 수행, 아직 분석 시작 안 함 |
| POST `/api/reviews/{review_id}/runs` | RunRequest: request_key | 202 Run. 동일 세션·review_id·request_key 재전송은 기존 실행 반환, 새 key는 새 실행 |
| GET `/api/runs/{run_id}` | 본문 없음 | 200 Run. 현재 상태 조회 |
| GET `/api/runs/{run_id}/result` | 본문 없음 | 200 Result. 저장된 스냅샷; 아직 없으면 409 RESULT_NOT_READY |
| GET `/api/artifacts/{artifact_id}` | 본문 없음 | 200 파일 bytes. 미완성·없는 파일은 JSON 오류로 응답 |

초기 세션 접근은 동일 출처의 서버 발급 opaque cookie를 쓰는 임시안이다. 운영 시 HttpOnly·Secure·SameSite=Lax와 변경 요청의 Origin 검증을 적용하고, session_id·run_id·artifact_id만으로 권한을 부여하지 않는다. JSON·URL·로그에 접근용 cookie 값을 넣지 않는다. 별도 회원가입은 초기 규격에 추가하지 않으며 “본인”은 해당 임시 세션 보유자를 뜻한다.

초기 polling은 실행 중 2초, heartbeat는 결과 조회 종료 후에도 60초 주기로 분리하는 개발 기본값이다. 유예는 마지막 유효 heartbeat부터 30분이며 호출 주기는 부하·브라우저 실험 후 조정한다. 단순 GET·잘못된/만료 세션 요청으로 수명을 연장하지 않는다. 새로고침 시 유효 cookie와 실행 ID로 복구하며, 만료 세션을 heartbeat로 부활시키지 않는다.

`DELETE` 후 cookie를 지우고 재조회는 인증 실패로 처리한다. cookie가 남아 있고 서버가 만료를 식별할 수 있으면 410 SESSION_EXPIRED를 반환한다. 브라우저 이탈 이벤트만으로 DELETE를 호출하지 않는다. 실행 중 삭제는 [호스팅 초기안](hosting-requirements.md)에 따라 안전한 중단·정리를 거친다.

## 4. 실행·진행·오류

`Run`은 실행/입력 ID, 후보별 진행, 단계 상태, 설정 버전, 시작·종료·갱신 시각, 오류, `result_available`을 담는다. 작업 상태는 기존 `queued / running / completed / partial / failed / interrupted`를 유지한다.

단계 ID는 `input_mapping / evidence_review / prediction / structure_comparison / reporting`로 임시 고정한다. 단계 상태는 `pending / running / completed / skipped / held / failed`다. 조건부 단계이므로 고정 개수 기반 완료율을 만들지 않는다. 후보 진행과 단계 목록은 candidate_id에 연결하며, 현재 단계는 `current_step`으로 표시한다.

| 의미 | 임시 처리 |
|---|---|
| 계획적 생략·자료 부족 보류 | 단계 skipped/held에 이유 저장. 검토가 끝나면 전체 completed 가능 |
| 유효 결과와 실행 실패 공존 | 전체 partial, result_available=true, 실패 근거·범위 유지 |
| 유효 결과 없음 | failed, result_available=false. 실제 산출물 없는 성공 표시 금지 |
| worker 소실 | interrupted. 저장된 유효 결과가 있으면 조회 가능하지만 성공·즉시 재실행으로 해석하지 않음 |
| 결과 만료 | Session·ApiError로 표현. 이미 completed인 분석 상태를 failed로 변경하지 않음 |

`ApiError`는 code·message·run_id/candidate_id/step_id·field_errors·retry_action을 포함한다. field_errors의 path는 ReviewInput을 기준으로 한 JSON Pointer다. retry_action은 `none / fix_input / retry_read / check_run / new_run`이며 프런트가 재호출 가능성을 자의적으로 판단하지 않도록 한다.

| HTTP·코드 | 사용처 |
|---|---|
| 422 INPUT_INVALID | 필드·파일 manifest 검증 실패, fix_input |
| 401 SESSION_REQUIRED / 410 SESSION_EXPIRED | 세션 없음·확인된 만료. 새 세션은 새 실행이며 이전 자료 복구 약속 안 함 |
| 404 NOT_FOUND | 없는 자료 또는 다른 세션의 자료. 존재 여부를 구별해 노출하지 않음 |
| 409 RESULT_NOT_READY | 결과 스냅샷 없음. check_run |
| 413 INPUT_TOO_LARGE / 429 CAPACITY_EXCEEDED | 입력/접수 제한. 상한·대기 시간은 서버 설정 후 확정 |
| 500 INTERNAL_ERROR / 503 SERVICE_UNAVAILABLE | 서비스 오류. 세부 경로·키·원문을 응답에 포함하지 않음 |

분석 실행 내부 오류는 Run.error에 저장한다. 그 오류를 담은 상태 조회 자체가 성공하면 HTTP 200이다. 외부 호출 timeout은 자동 new_run 대신 check_run을 우선하며 새 request_key를 자동 생성해 재접수하지 않는다.

## 5. 결과와 3D 데이터

`Result`는 run_id·review_id·candidate_ids·생성 시각·설정 버전과 structures·conditions·evidence·opinions·artifacts를 담는다. 후보 이름은 입력을 참조하고 순서나 이름으로 조인하지 않는다.

| 자료형 | 핵심 관계 |
|---|---|
| Structure | 구조 ID→artifact_id, 후보 ID, experimental/predicted 종류, 출처, model/assembly, chain_mapping, residue_mapping, alignment |
| Condition | 후보와 하나 이상의 구조, core/context 종류, 실제 포함 성분·자료 공백·출처 |
| Evidence | 후보→조건→선택 구조, 항목·종류, 측정 상태·값·단위·정의·근거 위치·출처 |
| Opinion | 후보→조건→항목, reviewable/needs_confirmation/hold/not_assessed, 근거 ID, 이유·상충 근거·한계·후속 질문 |
| Artifact | 구조/JSON/CSV 역할, pdb/mmcif/json/csv 형식, ready/missing/mock 상태, 파일명·크기·해시 |

Evidence의 measurement_state는 `measured / unknown / not_applicable / not_run / failed`다. measured일 때만 숫자 value와 unit·definition이 있고 나머지는 value=null과 reason이 필수다. 측정된 0은 그대로 0이다. 임계값·효능·종합 점수는 이 계약에 추가하지 않는다.

잔기 위치에는 model 번호, author/label 사슬, author/label 잔기 번호·삽입 코드·원서열 위치와 좌표 유무를 둔다. 사슬의 생물학적 역할은 chain_mapping으로 받는다. assembly 변환으로 복제된 단위는 operator_id로 구별하며 미정이면 null이다. 누락 구간을 viewer 좌표로 만들지 않는다.

alignment는 기준 구조·기준/대상 잔기 목록·4×4 변환·적용 여부·좌표 단위를 담는다. matrix는 row-major 배열로 저장하고 열벡터 `[x,y,z,1]`에 곱해 대상→기준 좌표로 변환한다. applied=true인 파일에는 재적용하지 않는다. 로직이 다른 규약을 쓰면 adapter가 변환하고, 기준이 없으면 null로 둔다.

구조 파일은 `/api/artifacts/{artifact_id}`로만 조회한다. 실제 파일·해시 없이 ready라고 표시하지 않는다. mock artifact는 다운로드·실제 3D 로딩을 비활성화한다. 현재 fixtures의 완료·보류 표시는 UI 상태 재현이며 구조 계산·실제 보고서 생성 완료가 아니다.

화면·보고·JSON·CSV는 같은 Result를 사용한다. JSON/CSV의 bytes·hash는 완성된 파일의 별도 Artifact 메타데이터로 계산하고, JSON export는 자기 파일의 hash를 내부에 넣지 않는다. 구조·근거·의견의 동일성으로 화면과 export를 대조한다.

## 6. 실제 로직으로 바꿀 위치

서비스 worker 운영부는 입력 접수·세션·DB 점유·파일 수명을 맡고, **logic adapter**는 입력 정규화·로직 진입·진행 변환·결과 변환을 맡는다. 프런트는 서비스 계약만 읽고 공급자 JSON·로직 내부 경로를 읽지 않는다.

| 방향 | 임시 계약 | 변경 시 책임 |
|---|---|---|
| 서비스→adapter | LogicRequest: run_id·review_id·input·settings_version·data_mode·work_dir·업로드별 서버 파일 참조 | 실제 함수명·인수·파일 방식에 맞춰 adapter가 변환 |
| adapter→서비스 진행 | ProgressUpdate: run_id·candidate_id·step_id·status·reason·updated_at | 로직의 이벤트를 이 형태로 정규화. DB 기록·최종 상태 집계는 서비스 운영부 |
| adapter→서비스 결과 | LogicOutput: Result와 files의 artifact_id·서버 내부 path | 필드명·번호 체계·단위·정렬 변환·출처를 adapter에서 대응. 서비스가 파일과 해시를 확인한 뒤 공개용 Artifact 등록 |
| 서비스→프런트 | 위 HTTP 계약 | 의미가 유지되면 화면 변경 없이 교체. 새로운 결과 종류·분기가 필요하면 계약 버전과 관련 화면 변경 |

work_dir와 파일 경로는 서버 내부에서 발급·검증하며 브라우저 입력이나 응답으로 쓰지 않는다. 새로운 필드가 왔다고 누락값을 임의 수치로 채우지 않는다. 버전 변경 시 schema·fixtures·변환 검증을 함께 갱신하며 호환되지 않는 의미 변경은 새 버전으로 구분한다.

LogicOutput의 파일은 서비스가 배정한 work_dir 안에 있어야 하며 결과 artifact_id와 일대일로 대응한다. mock/missing artifact에는 실제 파일을 요구하지 않는다. 실제 파일 인계·사슬/잔기·정렬·출처 대응과 live 완료 요건은 adapter 연결 단계에서 추가 검증한다. JSON Schema만으로 파일 존재·경로 경계·과학적 유효성을 확인했다고 판단하지 않는다.

## 7. 이 규격으로 시작할 작업 순서

1. 화면의 서비스 client를 mock/live 교체 가능하게 두고 fixtures로 입력·진행·비교·보고·오류·만료 상태를 구현한다. 구조 없는 mock은 3D 빈 상태를 보여준다.
2. FastAPI·DB·worker 운영부와 Docker 환경을 이 계약으로 연결한다. mock worker는 외부 모델을 호출하지 않고 시나리오만 반환한다.
3. 별도 공개 구조와 실제 대응표를 받아 Mol* 로딩·표→잔기 선택을 검증한다. fixture 수치를 계산값처럼 만들지 않는다.
4. 로직 담당의 실행부를 adapter에 연결해 스키마·ID·단위·상태 검증을 통과시키고 실제 모델 호출·배포 자원을 측정한다.

1–2는 로직 완성을 기다리지 않고 진행할 수 있다. 이 문서 작성은 임시 계약 준비 단계이며 프런트·API·Docker 구현 완료가 아니다. 실제 공개 배포의 공급자 조건·계정·예산은 [호스팅 조사](hosting-requirements.md)의 남은 항목을 따른다.

## 8. 검증 실행과 범위

저장소 루트에서 `uv run --no-project --with jsonschema python docs/frontend-hosting/contracts/validate-contract.py`를 실행한다. uv가 없는 환경에서는 jsonschema가 설치된 Python으로 같은 파일을 실행할 수 있다.

2026-09-25 검증: JSON Schema 자체와 9개 모의 시나리오가 통과했고, 중복 후보·다른 실행의 결과·다른 후보의 근거·없는 근거 참조·결과 존재 표시 오류·미확인 값의 0 변환·mock/live 혼동·만료 후 내용 노출·보류 이유 누락의 9개 잘못된 변형을 거부했다. 별도로 측정된 값 0은 스키마가 허용하는 것을 확인했다.

현재 예시는 실제 구조·좌표·파일 bytes를 포함하지 않으며 3D 연결·파일 인계·HTTP 상태 코드·cookie·삭제·과학적 분석의 런타임 검증은 아니다. 이 스크립트는 개발용 fixture 검증기이고 서버 입력·권한·로직 출력 검증의 구현을 대신하지 않는다.
