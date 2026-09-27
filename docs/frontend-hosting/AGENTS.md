# 프런트엔드·백엔드·호스팅 작업 가이드

## 1. WHAT — 역할

<!-- prev: 2026-09-26 update 전에는 분석 로직을 읽고 구현 자료·미결정 사항을 정리하는 조사 가이드였다. -->
HER2 서비스의 입력·진행·비교·보고 화면, 백엔드 접수·저장·조회와 worker 운영, 호스팅 준비를 안내한다. 분석값·판정·분석 워크플로우는 로직 담당의 책임이며, 서비스는 합의된 결과를 검증·저장·표시한다.

## 2. CONTENTS — 파일과 형식

- [3d-viewer.md](3d-viewer.md) — 3D 파일·표현·뷰어 비교, 실험 좌표 이미지와 구현 전 검토
- [result-presentation-research.md](result-presentation-research.md) — 전문가 결과 검토·AI 시대 변화와 시각 중심 출력 구조 제안
- [bio-agent-experience.md](bio-agent-experience.md) — 분석·소개·팀 탭과 바이오 에이전트 표현 기준
- [researcher-ux-research.md](researcher-ux-research.md) — 전문가 UX 근거·화면 가설·인터뷰·평가안
- [nvidia-design-research.md](nvidia-design-research.md) — NVIDIA 공식 디자인 출처·적용 근거·범위
- [design-guide.md](design-guide.md) — 사용자 확인 시각 방향과 토큰·표현 기준
- [screen-plan.md](screen-plan.md) — 네 화면·상태·임시 구현 범위
- [overview.md](overview.md) — 조사 범위·확인 상태·사용자 인터뷰·후속 작업
- [agent-logic.md](agent-logic.md) — 분석 분기·산출물·공개 구조에서 확인한 연결 주의점
- [frontend-contract.md](frontend-contract.md) — 화면이 소비할 데이터·상태·3D 연결·계약 검토 항목
- [hosting-requirements.md](hosting-requirements.md) — 실행·저장·외부 호출·배포 조건과 실측 인계
- [hosting-guide.md](hosting-guide.md) — AWS·Docker 입문 설명, 호스팅 비교·공식 가격·선택 조건 조사
- [server-rehearsal.md](server-rehearsal.md) — 배포 전 HTTPS·이미지·재시작·격리 복구 검증 절차
- [local-e2e.md](local-e2e.md) — 사용자 로컬 실제 E2E 절차·모델 호출 구분·확인 항목
- [runtime-files.md](runtime-files.md) — 실행 파일별 용도·호출 경로·검증 경계
- [runtime-audit.md](runtime-audit.md) — 실행·모의 경로, 코드 용도, 설계 차이와 운영 준비를 막는 문제의 재현·수정 우선순위
- [backend-deployment-plan.md](backend-deployment-plan.md) — 백엔드·Docker·AWS·HTTPS 준비 순서, CI/CD 도입과 검증·복구·운영 계획
- [temporary-contract.md](temporary-contract.md) — 사용자 요청으로 먼저 정한 v0.1.0 서비스 개발용 임시 규격
- [contracts/service.schema.json](contracts/service.schema.json) — 임시 입력·출력의 JSON Schema 원본
- [test-data.md](test-data.md) — 사이트 기본 공개 입력의 선정·출처·예상 결과·검증 경계
- [fixtures/scenarios.json](fixtures/scenarios.json) — 합성 입력·9개 모의 상태 예시
- [contracts/validate-contract.py](contracts/validate-contract.py) — 스키마·참조·상태 및 잘못된 데이터 검사

형식은 Markdown이며 조사 기준일·출처·확인 수준을 유지한다.

현재 구현 참조:

- [frontend/src/](../../frontend/src/) — 입력·진행·비교·보고 화면, Mol* 표시, 서비스 응답 소비.
- [service/README.md](../../service/README.md) — 두 API 경로와 로컬 실행 절차. `service/operational.py`는 영속 접수·조회·세션·파일 접근, `service/worker.py`는 mock/live 작업 점유·진행·정리, `service/live.py`는 로직 실행·파일 검증 경계, `service/db.py`·`service/migrations/`는 저장소 준비다.
- [service/app.py](../../service/app.py) — `logic.flow`를 호출하는 별도 동기식 실제 분석 시연 API. 영속 API·worker와 통합된 경로가 아니다.
- [compose.yaml](../../compose.yaml), [Dockerfile.web](../../Dockerfile.web), [Dockerfile.api](../../Dockerfile.api), [Caddyfile](../../Caddyfile) — 로컬 HTTP의 web·api·worker·db와 일회성 migration 구성.
- [integration.yml](../../.github/workflows/integration.yml), [check_mock_flow.py](../../scripts/check_mock_flow.py), [service/tests/](../../service/tests/) — 빌드·계약·서비스·Compose mock 검사.

## 3. HOW — 수정 방법

[PRD](../PRD.md), [ARCHITECTURE](../ARCHITECTURE.md), [HER2 설계](../topics/her2/agent-design.md)를 기준으로 서비스에 필요한 내용을 연결한다. 사용자 답변은 overview.md에 기록하고 관련 상위 문서의 미결정 상태도 맞춘다.

- 프런트는 같은 실행·후보·조건의 결과를 입력→진행→비교→보고에 연결하고, 분석값·보류 이유를 재계산하거나 임의 판정으로 바꾸지 않는다. 3D는 제공된 구조·사슬·잔기 대응을 표시한다.
- 백엔드는 세션 소유권, 입력 검증, 접수·저장·조회·파일 전달과 worker의 점유·생존·중단·자료 정리를 맡는다. 분석 함수·판정·도구 선택은 로직 담당과 연결 계약을 맞춘다.
- 영속 경로는 `DATA_MODE=mock|live`를 허용한다. Compose 화면은 같은 출처의 `/api`를 사용하며 `VITE_PERSISTENT_SERVICE=1`로 빌드된다. 실제 연결은 저장형 worker·진행·파일 경로를 함께 검사하고 별도 동기 시연 API 결과로 대신하지 않는다.
- 호스팅은 로컬 Compose·CI 구현, 실제 분석 연결, 공개 배포를 나누어 기록한다. AWS·HTTPS·공개 실행 제한·백업 복구·CD는 준비 과제이며 계정·예산·도메인과 실행 근거 없이 완료로 바꾸지 않는다.

## 4. HOW NOT — 주의할 함정

- 소비할 데이터 목록을 확정 API·구현된 응답으로 기록하지 않는다.
- 공개 자료 조회와 실제 계산·모델 호출·3D 실행 검증을 구분한다.
- 모의 응답에 실제 분석처럼 보이는 수치·사슬 대응·후보 판정을 만들지 않는다.
- 세션 소유 결과 파일을 정적 공개 경로에 복사해 접근 검사를 우회하지 않는다. 로직이 생성한 파일도 실행 ID·완성 상태·경로·크기·해시를 검증한 뒤 전달한다.

## 5. WHERE — 의존성과 경계

기능·과학적 범위의 원본은 ../topics/her2/, 기술 선택의 원본은 ../ARCHITECTURE.md·../ADR.md다. 이 폴더는 서비스 소비 요구와 조사 근거를 관리하며 분석 기준을 독자적으로 확정하지 않는다.

서비스 작업의 코드 참조는 `../../frontend/`, `../../service/`, 루트 Docker·Compose·Caddy 설정과 서비스 CI다. `.github/`의 공통 설정은 [협업 가이드](../collaboration/AGENTS.md)도 따른다. 개발용 데이터 규격 원본은 `contracts/service.schema.json`이며 최종 로직 합의와 구분한다. 서비스는 `../../logic/`의 분석 결과를 소비하고, 로직의 분석 기준을 이 가이드에서 재정의하지 않는다.

## 6. WHY — 배경

로직 구현 전에 화면과 호스팅 작업을 시작할 수 있도록, 확정 범위와 공동 검토가 필요한 연결점을 구분한다.

이 분리는 로컬 서비스 검증을 진행하면서 실제 분석 연결·공개 운영의 미완료 상태를 드러내기 위한 것이다. worker 운영을 서비스가 맡는다고 분석 워크플로우까지 서비스 책임으로 바뀌지는 않는다.

## 7. COMMANDS — 검증

`git diff --check`와 변경 문서의 상대 링크·참조 대상 확인. 실행하지 않은 제품 검증은 통과로 기록하지 않는다.

임시 규격 검증: 저장소 루트에서 `uv run --no-project --with jsonschema python docs/frontend-hosting/contracts/validate-contract.py`. 과학적 분석·서비스 런타임·live API 검증을 대신하지 않는다.

현재 구현의 명령은 저장소 루트에서 실행한다.

- 프런트 타입 검사·빌드: `npm --prefix frontend run build`.
- 서비스 검사: `uv run --locked pytest service/tests -q`. DB 연동 검사는 서비스 테이블을 비우므로 별도 임시 PostgreSQL을 가리키는 `TEST_DATABASE_URL`이 필요하다. DB 검사가 생략된 결과를 전체 통과로 기록하지 않는다.
- 로컬 Compose 설정 확인: `docker compose --env-file .env.compose.local config -q`. 개인 환경 파일 준비와 기동·종료 절차는 [서비스 실행 안내](../../service/README.md)를 따른다.
- 기동된 로컬 mock 흐름 검사: `uv run --locked python scripts/check_mock_flow.py`. 실제 분석·공개 호스팅 검증과 구분한다.

자동 검사 정의는 [integration.yml](../../.github/workflows/integration.yml)에 있다. 정의 존재와 원격 실행 성공은 별도로 확인한다.

CI는 서비스·로직 통합 검사에 `uv run --locked pytest service/tests logic/tests -q`를 사용한다. 위 서비스 한정 검사와 대상이 다르다. CI와 Docker 빌드는 Node 25·Python 3.13을 사용한다. OS·이미지·실제 실행 결과는 여전히 구분해 기록한다.
