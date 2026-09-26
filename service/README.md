# 시연용 실행부

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
