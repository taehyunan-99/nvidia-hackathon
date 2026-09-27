# 서비스 실행

## 로컬 Docker 뼈대

저장소 루트에서 개인 설정 파일을 만들고 영숫자 비밀번호를 넣는다. 이 파일은 Git에서 제외된다.

```bash
test -e .env.compose.local || printf 'POSTGRES_PASSWORD=%s\nWEB_PORT=8080\n' "$(openssl rand -hex 16)" > .env.compose.local
chmod 600 .env.compose.local
docker compose --env-file .env.compose.local config -q
docker compose --env-file .env.compose.local up --build -d --wait
```

기본 주소 `http://127.0.0.1:8080`에서 정적 화면을 제공하고 `/api/*`는 영속 API로 전달한다.
로컬 설정의 `WEB_PORT`를 바꾸면 그 포트로 접속한다.
DB 준비 확인 후 migration을 한 번 실행하고 API를 시작한다. DB와 업로드는 이름 있는 볼륨에
저장된다. 종료할 때는 `docker compose --env-file .env.compose.local down`을 사용하며
데이터를 유지하려면 `down -v`를 사용하지 않는다. 비밀번호를 바꾸려면 기존 DB 볼륨의
자격 증명도 함께 관리해야 한다.

이 구성은 `127.0.0.1`의 HTTP 개발 환경이다. 기본 `DATA_MODE=mock`에서는 사용자가 입력한 표적·후보 서열과 선택 구조 파일을
영속 API에 접수하고 별도 worker의 모의 결과를 조회한다. `DATA_MODE=live`로 별도 격리 구성을 띄우면
같은 입력을 실제 로직에 전달하고 진행·결과·파일을 저장한다. 브라우저는 실행 모드를 API에서 읽으며,
새로고침하면 유효한 세션과 실행 ID로 다시 조회한다. 별도 동기식 `/api/review` 버튼은
이 Compose 화면에서 숨긴다. 로컬에서 worker를 따로 실행하려면 API와 같은
`DATABASE_URL`, `SERVICE_DATA_ROOT`를 설정하고 아래 명령을 사용한다.

```bash
uv run python -m service.worker --scenario scientific-hold --once
```

`completed`, `scientific-hold`, `partial`, `failed`는 모두 실제 분석을 하지 않는
모의 시나리오다. 실제 경로는 `DATA_MODE=live`와 `python -m service.worker --mode live --once`를 사용한다.
공개 구조 일치 입력은 키 없이 예측을 생략할 수 있으며, Nemotron·Boltz-2 호출에는 서버 worker의 `NVIDIA_API_KEY`가 필요하다.
`--once`를 빼면 대기 중인 실행을 계속 처리한다. 실제 경로는 한 번에 한 실행만 점유하고 나머지는 대기시킨다. worker는 점유가
만료된 실행을 `interrupted`로 기록하고 자동 재실행하지 않는다. 세션 삭제·만료 후에는
점유가 끝난 자료 파일을 정리한다. 공개 HTTPS·접수 제한과 AWS 자원 생성은 아직 별도 과제다. 로컬 HTTPS와 백업·복구 검증은 아래 서버 구성 사전 검증을 따른다.

## 서버 구성 사전 검증

별도 `compose.server.yaml`과 `.env.server.example`로 localhost HTTPS·Secure cookie·저장소 보존을 시험한다. 공개 구조와 분석 의존성은 API 이미지에 포함된다. 준비·재시작·격리 백업 복원은 [서버 검증 절차](../docs/frontend-hosting/server-rehearsal.md)를 따른다. 공개 접수 제한과 AWS 배포는 별도 검증 대상이다.

## 영속 접수 API 준비

`service.operational`은 임시 계약 v0.1.0의 세션·입력·실행 접수와 조회를
PostgreSQL에 저장한다. 별도 `service.worker`를 실행하면 저장된 실행을 처리한다.
시연용 `service.app`의 동기식 `/api/review`와 경로·저장소를 공유하지 않는다.

로컬 PostgreSQL을 준비한 뒤 `DATABASE_URL`과 `SERVICE_DATA_ROOT`를 설정한다.
비밀값은 `.env.example`에 넣지 않는다. 운영 API는 다음 순서로 실행한다.

```bash
uv sync
uv run python -m service.db
uv run uvicorn service.operational:from_environment --factory --port 8011
```

`DATA_MODE=mock|live`를 허용한다. `/api/config`는 현재 모드만 반환한다. `/api/session`으로 받은 HttpOnly cookie로
검토와 실행을 접수한다. `ALLOWED_ORIGINS`에는 브라우저의 정확한 출처를
쉼표로 구분해 넣는다. HTTPS에서는 `SECURE_COOKIE=true`로 설정한다.
`MAX_UPLOAD_BYTES` 기본값은 파일당 20 MiB의 **개발용 제한**이며 대표 입력과
호스팅 용량을 측정한 뒤 다시 정한다. 파일은 서버가 정한 경로에 저장한다.

PostgreSQL 연동 검사는 별도의 임시 DB를 가리키는 `TEST_DATABASE_URL`이
필요하며, 검사 중 해당 DB의 서비스 테이블을 비운다.

```bash
TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/postgres uv run pytest service/tests -q
```

이 API와 worker는 로컬 검증용 접수 제한을 적용한다. `MAX_SESSION_RUNS=1`은 세션당 대기·진행 실행 수,
`MAX_ACTIVE_RUNS=10`은 유효한 전체 세션의 대기·진행 실행 수다. 같은 접수 키의 재시도는 같은 실행을 반환한다.
`ANALYSIS_TIMEOUT_SECONDS=1200`을 넘긴 분석 프로세스는 종료하고 실패로 남기며 자동 재실행하지 않는다.
이 값은 해커톤 로컬 검증 기본값이다. 추가로 변경 요청 빈도·활성 세션 수·세션 입력 수·요청 크기/수신 시간과 DB+파일 용량 경계값을 적용한다. 설정과 사용자 테스트 절차는 [로컬 E2E](../docs/frontend-hosting/local-e2e.md)를 따른다.
공개 서비스에는 아직 연결하지 않는다.

만료·삭제 후 실행 점유가 해제되면 파일과 DB의 입력·실행·결과를 지운다. 최소 세션 만료 기록은 410 응답을 위해 남긴다.
파일 정리 실패 시 완료로 기록하지 않고 다음 정리에서 재시도한다. 백업 복원은 외부 접근 전에 만료 자료를 정리해야 한다.
`GET /api/runs/{run_id}/report.json|csv`는 같은 세션이 조회하는 Run/Result 스냅샷으로 보고서를 생성한다.
JSON은 상태·결과 전체, CSV는 실행·후보·근거·의견·출처를 포함한 행과 원본 record_json을 제공한다.
미확인 값은 빈 칸과 상태·사유로 보존하며 mock 보고서는 data_mode=mock을 유지한다.

준비된 결과 파일은 `artifact_files`에 실행 ID와 `artifacts/` 아래 상대 경로가 등록되고,
Result의 해당 항목이 `ready`이며 크기·SHA-256이 실제 파일과 일치할 때만 세션 소유자가
`GET /api/artifacts/{artifact_id}` 또는 실행 ID를 함께 확인하는 `GET /api/runs/{run_id}/artifacts/{artifact_id}`에서 받는다. 현재 mock worker는 ready 파일을 만들지 않는다.
같은 후보를 반복 실행해 파일 ID가 겹치면 실행 ID 없는 조회는 거부하므로 화면은 실행 ID가 포함된 경로를 사용한다.
현재 로직은 ready 구조를 결과에 기록하지만 `LogicOutput.files`는 빈 배열로 반환한다. 실제 worker는 예측 파일을 실행 폴더에서, 공개 실험 파일을 검증된 구조 목록에서 찾아 크기·해시를 다시 확인한다. 로직 담당이 파일 목록을 채우면 해당 경로의 계약과 검사를 다시 대조한다.
`GET /api/reviews/{review_id}`는 같은 세션의 저장된 입력을 새로고침 후 다시 보여준다.
PR과 main의 자동 검사는 `.github/workflows/integration.yml`에서 수행한다.

## 기존 시연용 실행부

프런트가 **실제 분석 결과**를 화면에 띄우게 하는 얇은 층이다.
계획서 [S-02](../docs/plan.md)의 전체 범위가 아니다 — DB·작업 점유·재접속·worker는 없다.
본선에서 정식 운영부로 옮길 때 이 파일을 늘리지 말고 자리를 옮긴다.

## 실행

```bash
python -m uvicorn service.app:app --port 8010 --reload
npm --prefix frontend run dev
```

프런트는 `VITE_API_BASE`(기본 `http://127.0.0.1:8010`)로 실행부를 찾는다.
같은 출처에 배포하면 빈 문자열로 둔다.

```bash
python -m pytest service/tests logic/tests -q
```

## 경계

- 분석 판단은 [로직 B](../logic/README.md)에만 있다. 여기서 지표를 만들지 않는다.
- 실행은 **동기**다. 실측 12초 기준으로 시연에는 충분하다. 중단·재접속·중복 접수는
  다루지 않으며 그 책임은 정식 운영부의 몫이다.
- 내보내기 전에 `Run`·`Session`·`LogicOutput`을 계약으로 검증한다.
  어기면 결과 대신 500을 낸다(`test_broken_result_is_not_served_as_success`).
- 키 값은 어떤 응답에도 싣지 않는다. `/api/health`는 `mask()`를 거친 요약만 준다.

## 엔드포인트

| 경로 | 하는 일 |
|---|---|
| `GET /api/health` | 키 유무와 사용 가능한 preset. 키 값은 노출하지 않는다 |
| `GET /api/presets/{name}` | 시연 입력을 `ReviewInput`으로 반환 |
| `POST /api/review` | 분석 실행. 프런트가 읽는 시나리오 파일 모양으로 반환 |

`POST /api/review` 본문은 `{"preset": "experimental"}` 또는 `{"input": <ReviewInput>}`.

| preset | 경로 | 키 필요 | 실측 |
|---|---|---|---|
| `experimental` | 공개 구조 일치 → 예측 생략 | 불필요 | 0.1초 |
| `prediction` | 변이체 후보 → Boltz-2 호출 | **필요** | 12.6초 |

`prediction`의 변이체는 중쇄 한 자리를 바꾼 **가상 입력**이다. 실재하는 항체가 아니며
예측 경로를 보이기 위한 것이다.

## 확인한 것

2026-09-26. 브라우저에서 두 경로 모두 실행해 화면까지 확인했다.
`prediction`은 실제 Boltz-2 호출이다(`call_log.jsonl`에 기록).

## 아직 아닌 것

- 동시 실행·중복 접수·취소를 다루지 않는다. 같은 요청을 두 번 보내면 호출도 두 번 나간다.
- 실행별 임시 폴더에 구조·보고서 snapshot을 남기지만 영속 세션 조회·만료 정리는 없다. 공개 운영은 영속 API를 사용한다.
- 인증이 없다. 개발용 CORS(localhost)만 열려 있다. 배포 전에 좁혀야 한다.
- 분당 호출 한도를 모른다. 연속 실행 시 동작은 미확인이다.
