# 서버 구성의 로컬 검증

목적: AWS 자원을 만들기 전에 동일 이미지로 HTTPS·DB·파일 보존·복구를 검증한다. 기본값은 loopback 전용 mock worker다. `DATA_MODE=live`를 별도 격리 구성에 설정하면 영속 worker가 실제 분석 로직을 실행한다. 공개 접수·AWS 배포 성공을 뜻하지 않는다.

## 이미지와 설정 준비

저장소 루트에서 실행한다. `compose.yaml`은 기존 HTTP 개발 환경이고 `compose.server.yaml`은 독립된 HTTPS 검증 환경이다. 두 파일을 합쳐 사용하지 않는다. Python 3.11 이상과 Docker Compose가 필요하다.

```sh
docker build -f Dockerfile.api -t her2-api:server-check .
docker build -f Dockerfile.web -t her2-web:server-check .
cp .env.server.example .env.server.local
chmod 600 .env.server.local
```

기존 `.env.server.local`이 있으면 덮어쓰지 않는다. `openssl rand -hex 24`로 만든 값을 해당 파일의 `POSTGRES_PASSWORD`에 넣는다. 비밀번호·세션 체크포인트·백업은 Git이나 채팅에 넣지 않는다. DB 비밀번호를 바꾸려면 기존 DB 계정도 함께 변경해야 하며 env 파일만 바꾸지 않는다.

API 이미지는 공개 구조 좌표·검증 목록·접촉 결과, 실제 사용하는 A-02 metrics 코드와 uv.lock의 분석 의존성을 포함한다. 개발 테스트·모델 측정 도구·연구 결과 묶음은 API 이미지에서 제외한다. NAT는 해당 checkout의 `pyproject.toml`·`uv.lock`에 따라 설치되므로 최신 에이전트 변경이 포함된 커밋으로 배포 이미지를 만들어야 한다. 구조 계산이 이미지 안에 있다는 사실은 worker 연결 완료를 뜻하지 않는다.

```sh
python3 scripts/check_server_config.py
export HER2_CHECK_PROJECT=her2-server-check
dc() { docker compose -p "$HER2_CHECK_PROJECT" --env-file .env.server.local -f compose.server.yaml "$@"; }
dc up -d --wait
mkdir -p tmp/server-check
dc cp web:/data/caddy/pki/authorities/local/root.crt tmp/server-check/root.crt
python3 scripts/check_server_flow.py create --ca tmp/server-check/root.crt --state tmp/server-check/state.json
```

최초 인증서 생성이 끝난 뒤 CA 파일을 복사한다. localhost 인증서는 로컬 CA가 발급하며 검사 스크립트에만 CA 파일을 전달한다. OS 신뢰 저장소를 바꾸거나 인증서 검증을 끄지 않는다. 브라우저에서 공개적으로 신뢰되는 인증서와는 다르다. [Caddy HTTPS](https://caddyserver.com/docs/automatic-https)

사전 검사는 잘못된 origin·취약한 비밀번호 형식·공개 포트 바인딩을 거부한다. 검증 단계에서 공개 노출은 막혀 있다. API·DB·worker는 외부 포트를 열지 않고 웹만 localhost의 8081/8443을 사용한다. 로그는 서비스별 10MB × 3개로 제한하고 서버 상주 컨테이너의 메모리 제한 합계는 2.75GiB, migration 포함 3.25GiB다. swap은 추가로 허용하지 않는다. 한도는 준비용 값이며 실제 분석 통합 후 재측정한다.

실제 연결은 별도 로컬 프로젝트의 비공개 env에 `DATA_MODE=live`를 설정해 확인한다. 공개 구조 입력은 `REQUESTS_CA_BUNDLE=<그 프로젝트의 root.crt> BASE_URL=https://localhost:<HTTPS 포트> uv run python -m scripts.check_live_flow`로 입력→진행→결과·파일 무결성·소유권을 검사한다. Nemotron·Boltz-2를 호출하려면 worker에만 비공개 `NVIDIA_API_KEY`를 전달하고 호출량·결과를 따로 기록한다. 기존 `check_server_flow.py`는 mock 전용 검사다.

## 재시작과 파일 보존

```sh
dc up -d --force-recreate --wait
python3 scripts/check_server_flow.py verify --ca tmp/server-check/root.crt --state tmp/server-check/state.json
dc cp scripts/check_server_storage.py api:/tmp/check_server_storage.py
dc exec -T api python /tmp/check_server_storage.py < tmp/server-check/state.json
```

같은 세션의 기존 입력·결과와 업로드 파일의 DB 참조·크기·SHA-256을 확인한다. `state.json`에는 검사용 세션 쿠키가 들어 있으며 생성 시 권한 600을 적용한다. 세션은 30분 뒤 만료되므로 오래된 체크포인트가 410을 반환하는 것은 복구 실패와 구별한다. `verify`는 새 작업을 만들지 않는다.

## 일관된 백업과 격리 복원

아래는 합성 입력·공개 구조를 넣은 **검증용 데이터**의 복구 실습이다. 해커톤 임시 입력·결과의 정기 운영 백업은 만들지 않는다. 검증용 백업은 복원 검사 후 폐기한다. 복원 시 API를 열기 전에 만료 자료를 정리한다. 만료 전 촬영한 백업은 이후 명시적 삭제를 알 수 없으므로 운영 사용자 자료를 복원하지 않는다.

```sh
umask 077
dc stop web api worker
dc exec -T db pg_dump -U her2 -d her2 -Fc > tmp/server-check/database.dump
dc run --rm --no-deps -T api tar -cf - -C /data . > tmp/server-check/uploads.tar
```

새 접수와 worker를 멈춘 같은 시점의 DB·업로드를 한 쌍으로 보관한다. 실모델 연결 후에는 중단 전 진행 작업·외부 요청 상태를 정리하는 절차가 추가로 필요하다. 기존 DB에 덮어써서 복구를 시험하지 않는다.

별도 `.env` 파일을 만들고 HTTPS/HTTP 포트를 8444/8082, origin을 `https://localhost:8444`로 바꾼다. DB 비밀번호는 백업 대상과 동일하게 사용하고 파일 권한은 600으로 둔다. 별도 Compose project 이름으로 빈 볼륨을 생성한다.

```sh
restore() { docker compose -p her2-server-restore --env-file tmp/server-check/restore.env -f compose.server.yaml "$@"; }
restore up -d --wait db
restore exec -T db pg_restore -U her2 -d her2 --no-owner --exit-on-error < tmp/server-check/database.dump
restore run --rm --no-deps --user 0 -T api tar -xf - -C /data < tmp/server-check/uploads.tar
restore run --rm --no-deps -T api python -c "import os; from pathlib import Path; from service.worker import reap, cleanup_sessions; d=os.environ['DATABASE_URL']; reap(d); cleanup_sessions(d, Path('/data'))"
restore up -d --wait
restore cp web:/data/caddy/pki/authorities/local/root.crt tmp/server-check/restored-root.crt
python3 scripts/check_server_flow.py verify --base-url https://localhost:8444 --ca tmp/server-check/restored-root.crt --state tmp/server-check/state.json
restore cp scripts/check_server_storage.py api:/tmp/check_server_storage.py
restore exec -T api python /tmp/check_server_storage.py < tmp/server-check/state.json
```

tar 복원은 파일 소유권을 복구하기 위해 일회성 root 컨테이너에서 수행한다. API·worker 런타임은 계속 UID 10001이다. 새 프로젝트는 별도 TLS CA를 만들며 기존 프로젝트의 TLS 데이터는 자체 볼륨에 남는다. 운영 인증서·키는 DB·업로드와 별개의 보호 대상이며 필요 시 별도 보관한다.

이미지 되돌리기는 이전 이미지 ID/digest와 해당 DB 스키마가 호환될 때만 수행한다. 호환되지 않으면 기존 볼륨을 파괴하지 말고 격리 복원으로 검증한 뒤 전환한다. `down`은 컨테이너를 정리하되 볼륨을 유지한다. `down -v`는 여기서 새로 만든 폐기 가능한 테스트 프로젝트를 종료할 때만 사용하며 운영 데이터에는 사용하지 않는다.

## 공개 배포 전 남은 조건

- 영속 worker의 모델 호출량·예측 파일과 보류/실패/중단 경로를 실제 서버 규격에서 재검증하고 공개 접수 제한을 정한다.
- 실제 도메인과 DNS·80/443·HTTPS origin·공개 접수 정책 확정. 현재 localhost 구성을 그대로 외부 공개하지 않는다.
- 서울 4GB 서버에서 실제 NVIDIA 경로와 전체 서비스를 재검증하고, 정확한 운영 날짜·계정 플랜·예산 알림·총비용 확인.
- 검증한 이미지 digest·설정·migration 버전을 기록하고 수동 배포·복귀 절차의 AWS 실행 확인.


## 이번 실행에서 확인한 결과

2026-09-26, Docker Desktop Linux arm64에서 다음을 직접 실행했다.

- 현재 작업 브랜치의 API·웹 이미지 빌드 성공. PR #19 병합 커밋 `bc04099`를 별도 빌드 context로 내보내 같은 Dockerfile 변경을 적용한 이미지도 빌드했으며 NAT 설정·공개 구조 2개·분석 의존성 및 `uv pip check`(164개 패키지) 통과. Git 병합은 하지 않았다.
- 인증서를 실제로 검증한 localhost HTTPS에서 입력·공개 구조 업로드·mock 작업·결과 조회, Secure/HttpOnly cookie, 익명 접근 차단 통과. HTTP 요청은 설정한 HTTPS 포트로 301 이동했다.
- 컨테이너 전체 강제 재생성 뒤 같은 CA·세션으로 기존 결과 조회 성공. 새 프로젝트의 빈 PostgreSQL·업로드 볼륨에 백업을 복원하고 DB 참조·파일 크기·SHA-256 일치 확인.
- 같은 DB 스키마를 사용하는 PR #19 이미지에서 기존 로직 이미지로 되돌린 뒤 결과 조회 성공. 복원된 세션의 만료 시각을 지나게 한 검사에서는 접근을 410으로 거부했다.
- 소스 마운트 없이 PR #19 검증 이미지 내부에서 A-02 46.19초·A-03 47.41초로 계산 완료(네트워크 차단, 1GiB 제한). 실제 모델 호출과 영속 worker 분석 연결은 이 검사에 포함되지 않는다.
- 잘못된 HTTP origin·약한 비밀번호 형식·공개 바인딩의 사전 검사 실패 확인. Python 구문·변경 문서 상대 경로·공백 검사 통과.

실제 서울 EC2·공개 CA·DNS·AWS 복구·원격 CD는 미검증이다. 로컬 테스트용 프로젝트만 종료했고 기존 개발 서비스는 유지했다. 검증용 체크포인트와 백업은 Git 제외 `tmp/server-check/`에 보관한다.


## 2026-09-27 재검증과 AWS 접근 확인

`1665688`에서 다시 만든 이미지로 격리 localhost HTTPS mock 흐름, Secure/HttpOnly 쿠키, 익명 차단, 컨테이너 강제 재생성 후 재조회, 일관된 DB·파일 백업과 별도 프로젝트 복원·파일 해시를 확인했다. CI의 mock 흐름 검사도 복원 환경에서 통과했다. 실제 모델 기본 시나리오의 새 실행은 [로컬 E2E 기록](local-e2e.md#2026-09-27-최종-기본-시나리오-리허설)에 구분했다.

사용자는 AWS 제공 도메인의 HTTPS 공개 배포를 요청했고, 유료 서버가 필요하면 기존 서울 리전·약 30일·크레딧 차감 전 총 10만 원 예산으로 진행하도록 확인했다. `her2-dev`의 만료된 로그인을 갱신해 EC2 인스턴스 0개를 확인했으나, IAM 사용자 `her2-cli`에는 CloudFront 목록 조회·계정 플랜 조회·EC2 보안그룹 생성 권한이 없었다. 보안그룹 생성은 dry-run으로만 확인했고 AWS 자원은 생성하지 않았다. 이후 사용자가 Bio3Deployment 정책을 생성했고, 연결 승인을 받아 her2-cli에 연결했다. CloudFront 목록 조회와 EC2 보안그룹 생성 dry-run이 통과했다. 처음에는 t3.medium만 허용했으나 사용자 승인으로 정책 v2를 저장해 무료 대상 c7i-flex.large로 변경하고 잘못된 CloudFront 작업명을 제거했다. 예산 자동 중지 역할 초안은 개인 검증 폴더에 준비했으나 역할·예산은 생성하지 않았다.

CloudFront 기본 `*.cloudfront.net` 주소에는 기본 HTTPS 인증서를 사용할 수 있다. 도메인 구매 비용이 없다는 뜻이며 EC2·디스크·전송 비용 전체가 무료라는 뜻은 아니다. [AWS 기본 인증서](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesGeneral.html)

예산 알림·EC2 자동 중지는 아직 설정하지 않았다. Budgets는 비용 집계 지연이 있으며 EC2 중지 후에도 EBS 비용은 남으므로 원화 10만 원의 절대 청구 상한으로 설명하지 않는다. 5만·7만 원 상당 알림과 8만 원 상당 자동 중지를 제안했으며, 실제 설정에는 수신 주소·중지 역할·달러 기준액과 운영 종료일 확인이 필요하다. [AWS Budgets 집계 주기](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-best-practices.html), [예산 동작](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-controls.html), [EC2 중지 후 비용](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html)

권한 연결 후 계정 플랜 조회에서 무료 플랜 ACTIVE·잔여 크레딧 $100·만료 예정 2027-03-26을 확인했다. 무료 플랜을 유료로 전환하기 전에는 카드 청구가 없고, 크레딧 소진 또는 만료 시 계정이 닫히는 조건이다. 서울 무료 플랜 대상 중 4GB인 c7i-flex.large는 시간당 $0.09576이며 30일 720시간·gp3 30GB·IPv4 한 개의 기본 합계는 $75.2832다. 기존 환율·세금 예산 가정(1,500원/USD·10%)에서는 약 124,217원으로 크레딧 차감 전 10만 원 기준을 초과하므로, 무료 플랜·크레딧 운영과 기존 총원가 기준 유지 중 사용자 선택을 확인한다. 실제 월별 청구·트래픽·추가 사용량의 확정 견적은 아니다. [AWS Free Tier FAQ](https://aws.amazon.com/free/free-tier-faqs/), [AWS 서울 EC2 가격표](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/ap-northeast-2/index.csv)

사용자가 AWS 준비를 계속하도록 요청한 뒤 무료 플랜용 c7i-flex.large 기준으로 준비했다. 운영자 접속 키와 CloudFront 전용 원본 포트·운영자 /32 SSH의 보안그룹을 생성하고 EC2 생성 dry-run을 통과했다. 실제 인스턴스·배포 주소는 main 병합 후 생성한다. 운영에 검증용 공유 누적 60/4 한도를 적용하려던 제안은 철회했으며 기존 분석 실행별 Nemotron 40·Boltz-2 4와 동시 분석 1건을 유지한다. [배포 설정·준비 상태·main 기준 절차](aws-deployment.md)를 따른다.
