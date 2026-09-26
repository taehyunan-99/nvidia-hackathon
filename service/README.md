# 서비스 실행

## 로컬 Docker 뼈대

저장소 루트에서 개인 설정 파일을 만들고 영숫자 비밀번호를 넣는다. 이 파일은 Git에서 제외된다.

```bash
test -e .env.compose.local || printf 'POSTGRES_PASSWORD=%s\nWEB_PORT=8080\n' "$(openssl rand -hex 16)" > .env.compose.local
chmod 600 .env.compose.local
docker compose --env-file .env.compose.local config -q
docker compose --env-file .env.compose.local up --build -d --wait
```

`http://127.0.0.1:8080`에서 정적 화면을 제공하고 `/api/*`는 영속 접수 API로 전달한다.
DB 준비 확인 후 migration을 한 번 실행하고 API를 시작한다. DB와 업로드는 이름 있는 볼륨에
저장된다. 종료할 때는 `docker compose --env-file .env.compose.local down`을 사용하며
데이터를 유지하려면 `down -v`를 사용하지 않는다. 비밀번호를 바꾸려면 기존 DB 볼륨의
자격 증명도 함께 관리해야 한다.

이 구성은 `127.0.0.1`의 HTTP 개발 환경이다. 현재 화면의 분석 시작은 기존 동기식
`/api/review`를 사용하지만 이 Compose의 API는 세션·입력·실행 **접수**만 제공한다.
따라서 화면 분석 흐름은 다음 연결 단계 전까지 동작하지 않으며, 접수된 실행도 별도
worker가 생기기 전에는 `queued`에 머문다. worker는 이후 같은 Python 이미지에 별도
실행 명령을 추가하고 DB·업로드 볼륨을 공유하는 서비스로 연결한다. HTTPS, 공개 접수
제한, 백업·복구, 실제 모델 호출과 AWS 자원은 아직 준비되지 않았다.

## 영속 접수 API 준비

`service.operational`은 임시 계약 v0.1.0의 세션·입력·실행 **접수와 조회**를
PostgreSQL에 저장한다. 별도 worker가 아직 없어 실행은 `queued`에 머문다.
시연용 `service.app`의 동기식 `/api/review`와 경로·저장소를 공유하지 않는다.

로컬 PostgreSQL을 준비한 뒤 `DATABASE_URL`과 `SERVICE_DATA_ROOT`를 설정한다.
비밀값은 `.env.example`에 넣지 않는다. 운영 API는 다음 순서로 실행한다.

```bash
uv sync
uv run python -m service.db
uv run uvicorn service.operational:from_environment --factory --port 8011
```

현재는 `DATA_MODE=mock`만 허용한다. `/api/session`으로 받은 HttpOnly cookie로
검토와 실행을 접수한다. `ALLOWED_ORIGINS`에는 브라우저의 정확한 출처를
쉼표로 구분해 넣는다. HTTPS에서는 `SECURE_COOKIE=true`로 설정한다.
`MAX_UPLOAD_BYTES` 기본값은 파일당 20 MiB의 **개발용 제한**이며 대표 입력과
호스팅 용량을 측정한 뒤 다시 정한다. 파일은 서버가 정한 경로에 저장한다.

PostgreSQL 연동 검사는 별도의 임시 DB를 가리키는 `TEST_DATABASE_URL`이
필요하며, 검사 중 해당 DB의 서비스 테이블을 비운다.

```bash
TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/postgres uv run pytest service/tests/test_operational.py -q
```

이 API는 로컬 접수 단계다. worker 점유·결과 등록·만료 자료의 물리적 정리,
HTTPS·공개 접수 제한은 다음 단계에서 구현·검증한다. 공개 서비스에
연결해서는 안 된다.

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
- 결과를 보관하지 않는다. 응답을 놓치면 다시 실행해야 한다.
- 인증이 없다. 개발용 CORS(localhost)만 열려 있다. 배포 전에 좁혀야 한다.
- 분당 호출 한도를 모른다. 연속 실행 시 동작은 미확인이다.
