# AWS 무료 플랜 배포 준비

2026-09-27 기준. 실제 서비스는 **PR 병합 후 main의 확정 커밋으로** 배포한다. 이 문서의 준비 완료와 EC2 기동·공개 HTTPS 검증은 구분한다.

## 구성과 현재 확인

- 서울 `ap-northeast-2`, 무료 플랜 대상 `c7i-flex.large` 1대(2 vCPU·4 GiB), 암호화 gp3 30GB, 같은 서버의 PostgreSQL·API·worker·웹. 자동 증설·별도 DB·로드밸런서·NAT Gateway는 사용하지 않는다.
- 계정 조회 당시 FREE·잔여 크레딧 $100. 30일 720시간의 서버·디스크·공인 IPv4 기본 합계는 $75.2832이며 트래픽 등 추가 사용량은 별도다. 무료 플랜의 크레딧 소진·기간 만료는 서비스 중단으로 이어지며 유료 플랜으로 자동 변경하지 않는다. 기존 환율·세금 가정의 차감 전 10만 원 기준과는 다른 크레딧 운영안이다.
- `Bio3Deployment` 정책 v2에 무료 대상 서버 유형을 적용했다. `bio3-web` 보안그룹과 `bio3-deploy` 접속 키를 생성했고, CloudFront 원본용 prefix list의 TCP 80과 현재 운영자 IPv4 `/32`의 TCP 22만 허용했다. API·DB 포트는 열지 않았다.
- 위 설정의 EC2 `run-instances --dry-run`은 `DryRunOperation`으로 권한 검사를 통과했다. 실제 인스턴스·CloudFront 배포는 아직 없으며 프리 티어 자원 제한·가용 용량·실제 기동은 생성 시 별도 확인한다.
- CloudFront 관리형 정책 ID를 계정에서 조회했고 생성 입력은 SDK 스키마로 검증했다. AWS CLI의 출력 예시 생성은 자동으로 만든 OriginGroups 예시의 길이 오류로 실패했으나 실제 생성 요청은 보내지 않았다.

개인 계정의 자원 ID·접속 키·검증 근거는 Git 제외 `tmp/aws-https-deploy/`에 있다. 다른 checkout에 존재한다고 가정하지 않는다. 개인 키는 별도 안전한 위치에도 보관하며 저장소에 넣지 않는다.

## HTTPS와 접근 경계

[compose.server.yaml](../../compose.server.yaml)에 [compose.aws.yaml](../../compose.aws.yaml)을 덧씌우고 [Caddyfile.aws](../../Caddyfile.aws)를 사용한다. **브라우저→CloudFront는 HTTPS, CloudFront→EC2는 HTTP**다. 원본 접근은 보안그룹의 CloudFront prefix list와 256비트 임의 `X-Bio3-Origin` 값 검사를 함께 사용한다. 종단 간 TLS라고 설명하지 않는다. 원본 구간까지 암호화하려면 별도의 도메인·인증서 또는 네트워크 구성이 필요하다.

CloudFront는 AWS 기본 `*.cloudfront.net` 도메인·인증서를 사용한다. 전체 경로에 `Managed-CachingDisabled`와 `Managed-AllViewerExceptHostHeader`를 적용해 세션 쿠키·요청 헤더·query string을 전달하며 결과·Set-Cookie를 공유 캐시로 제공하지 않는다. 오류 캐시 TTL도 0이다. 임시 결과를 S3나 웹 정적 경로에 복사하지 않는다.

운영은 기존 실행별 제한을 유지한다: **분석 한 건당 재시도 포함 Nemotron 40회·Boltz-2 4회**, 실제 분석 동시 1건, 대기·진행 합계 최대 10건, 세션당 진행 1건, 실행 시간 1200초. 공개 운영의 `MODEL_BUDGET_PATH`는 비워 실행별 계수를 사용하며, 소진된 내부 검증용 공유 계수를 초기화하거나 재사용하지 않는다. 공개 테스트의 기본 일일 합계는 재시도 포함 Nemotron 4,000회·Boltz-2 200회다. `NEMOTRON_DAILY_REQUEST_LIMIT`·`BOLTZ2_DAILY_REQUEST_LIMIT`으로 조정하며 한국시간 자정을 기준으로 다음 날짜의 한도를 사용한다. 공유 `/data/model-daily-budget.sqlite3`에 날짜별 사용량을 보존하므로 worker 재시작·새 분석으로 같은 날 한도를 초기화하지 않는다. 실행별·일일 계수를 하나의 SQLite 트랜잭션으로 예약하며 한도 초과 요청은 전송 전에 거부한다. 이는 서비스가 정한 운영 상한이며 NVIDIA가 보장한 무료 허용량이 아니고, 공급자 계정 한도·429는 별도로 따른다. 기본값은 공개 테스트를 위한 여유 있는 서비스 상한이며 실제 일일 처리량을 보장하지 않는다.

## main 병합 후 배포 순서

1. main과 원격 main의 확정 커밋이 일치하는지 확인하고, 해당 커밋의 파일만 아카이브한다. 개인 env·키·세션·테스트 백업은 제외한다. 작업 브랜치의 미커밋 파일이나 기존 로컬 arm64 이미지를 x86 서버 배포물로 사용하지 않는다.
2. 개인 `ec2-launch.json`의 AMI·subnet·보안그룹·키·서버 유형을 다시 확인하고 1대만 생성한다. 현재 운영자 IP가 바뀌었으면 기존 `/32` 규칙을 교체하며 SSH를 `0.0.0.0/0`으로 열지 않는다. IMDSv2 필수·암호화 gp3 30GB·OS 종료 시 stop을 유지한다. 원래 계정과 FREE 상태를 다시 확인하며 유료 전환 요구는 자동 수락하지 않는다.
3. 실제 EC2 공개 DNS·IP·인스턴스 ID를 개인 기록에 저장한다. SSH 호스트 키는 EC2 콘솔의 시스템 로그 등 별도 AWS 경로와 대조하고 `StrictHostKeyChecking=no`로 우회하지 않는다. Amazon Linux 2023의 Docker 및 공식 Docker Compose CLI 플러그인을 설치한다(로컬 검증 5.1.2, `!override` 지원에는 2.24.4 이상 필요). main 아카이브를 전송하고 서버에서 `Dockerfile.api`·`Dockerfile.web`을 빌드해 linux/amd64와 이미지 ID를 기록한다.
4. [.env.aws.example](../../.env.aws.example)을 `.env.aws.local`로 복사하고 권한 600으로 둔다. DB 비밀번호는 임의 48자리 이상 hex, 원본 확인값은 임의 64자리 hex로 생성하고 이미지에는 기록한 `sha256:` ID를 넣는다. 첫 검증은 `DATA_MODE=mock`·모델 키 없음으로 시작한다. CloudFront hostname과 origin은 다음 단계의 실제 반환값을 넣는다.
5. [prepare_cloudfront.py](../../scripts/prepare_cloudfront.py)로 실제 EC2 공개 DNS와 동일한 원본 확인값을 담은 생성 JSON을 권한 600 파일로 준비한다. `aws cloudfront create-distribution-with-tags --distribution-config-with-tags file://<생성 JSON> --profile her2-dev`로 한 번 생성한다. 동일한 파일의 CallerReference를 유지하고 실패했다고 새 distribution을 반복 생성하지 않는다. 반환된 ID·도메인을 기록해 `SITE_ADDRESS=<실제 hostname>`, `PUBLIC_ORIGIN=https://<실제 hostname>`으로 설정한다.
6. 아래 사전 검사를 통과한 뒤 Compose를 기동한다. CloudFront 상태가 Deployed가 된 후 실제 HTTPS 인증서·HTTP 리디렉션·정적 파일·세션·입력 접수·결과·다른 세션 차단을 확인한다. CF·서버 어느 쪽도 비밀 설정 전체를 로그에 출력하지 않는다.

```sh
python3 scripts/prepare_cloudfront.py --origin-domain "$BIO3_ORIGIN_DNS" --env-file .env.aws.local --output tmp/cloudfront-create.json
python3 scripts/check_aws_config.py --env-file .env.aws.local
docker compose -p bio3 --env-file .env.aws.local -f compose.server.yaml -f compose.aws.yaml up -d --wait
```

7. 실제 모델 경로는 mock 확인 후 worker에만 비공개 NVIDIA 키를 전달하고 API·worker의 `DATA_MODE=live`를 함께 적용한다. 운영자가 승인한 대표 실행 한 건으로 입력→모델·계산→파일 해시·JSON/CSV→3D→새로고침 복원을 검증한다. 과거 로컬 모델 성공을 AWS 모델 성공으로 기록하지 않는다.
8. 첫 기동에서 30일 뒤의 UTC 종료 시각을 확정한다. EC2 내부에 영속 systemd timer(`OnCalendar=<종료 UTC>`, `Persistent=true`)와 `/usr/sbin/shutdown -h now`를 실행하는 oneshot service를 설치해 자동 stop을 예약하고 `systemctl list-timers`로 확인한다. 재배포 때 종료 시각을 뒤로 밀지 않는다. 인스턴스 중지 후에도 EBS는 남으므로 종료 시 자료 필요 여부를 확인한 뒤 별도로 정리한다. 현재는 이 타이머를 설치할 서버가 없으며 예약 완료 상태가 아니다.

## 검증·재배포·복구

[check_aws_config.py](../../scripts/check_aws_config.py)는 비밀 파일 권한·고정 이미지·정확한 HTTPS origin·Secure cookie·비공개 DB/API·요청 한도를 확인한다. 실제 SG·인증서·CloudFront 전달·CPU/RAM·NVIDIA 한도는 원격 검증 대상이다. 로컬에서 허용되지 않은 원본 헤더를 403으로 거부하고 올바른 헤더의 정적/API 응답을 확인했다. HTTP origin·공유 검증 계수·변하는 이미지 태그를 넣은 잘못된 설정도 거부했다.

재배포 전 새 접수와 진행 작업을 정리한 뒤 이전 main SHA·이미지 ID·DB schema·환경 파일을 기록한다. 호환되는 schema라면 이전 이미지 ID로 되돌리고 같은 세션의 결과·파일 조회를 재검증한다. 비호환 migration을 자동 되돌리거나 운영 볼륨에 복원하지 않는다. 검증용 자료의 일관된 백업·별도 볼륨 복원은 [서버 리허설](server-rehearsal.md#일관된-백업과-격리-복원)을 따르며 임시 사용자 자료를 무기한 백업하지 않는다.

`docker compose down`은 볼륨을 보존하고 운영 환경에서 `down -v`는 사용하지 않는다. EC2 stop/start로 공개 IP·DNS가 바뀌면 CloudFront origin을 새 DNS로 갱신하고 접속을 재검증한다. 원본 확인값을 바꿀 때도 CloudFront와 웹 설정을 함께 갱신한다. 종료 후 디스크·주소·이미지 등 남은 자원을 확인한다.

## 공식 근거

- [AWS 무료 플랜·크레딧](https://aws.amazon.com/free/free-tier-faqs/), [EC2 무료 대상](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-launch-parameters.html), [서울 가격표](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/ap-northeast-2/index.csv).
- [CloudFront 기본 인증서](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesGeneral.html), [원본 설정](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesOrigin.html), [쿠키 전달](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Cookies.html).
- [NVIDIA API Catalog 개발·검증 용도](https://docs.api.nvidia.com/nim/docs/run-anywhere). 계정별 현재 요청 제한은 공급자 계정 화면에서 확인하며 과거의 고정 무료 크레딧 수를 현재 한도로 가정하지 않는다.

## 준비 검증 결과

프런트 24개 검사·빌드·브라우저의 완료 후 조회 중단·세션 만료 확인을 통과했다. 일일 한도 변경 후 격리 PostgreSQL을 포함한 제품 검사 334 passed·3 skipped(선택 실행 실모델 2개·호스트에 없는 고정 Probe 1개), 호출 한도·재시도·한국시간 날짜 경계 집중 검사 33 passed를 확인했다. 집중 검사에는 전체 검사 시작 후 추가한 전송 전 차단·한국시간 자정 사례가 포함된다. 새 API·웹 이미지의 로컬 빌드와 네트워크 차단 컨테이너에서 5건 이상의 별도 분석 예약·새 컨테이너의 같은 날 계수 보존·한도 초과 차단을 확인했다. 새 NVIDIA 호출은 없다. 이 이미지들은 로컬 arm64 검증용이며 실제 배포는 main의 x86 이미지로 다시 수행한다.
