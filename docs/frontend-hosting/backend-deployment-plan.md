# 백엔드 준비부터 AWS 배포까지의 작업 계획

<!-- prev: 2026-09-26 초기 상태는 로컬 접수 API와 web·api·db Docker 뼈대 구현, 이후 단계는 계획이었다. -->
작성일: 2026-09-26. 상태 갱신: **영속 mock API·worker, web·api·worker·db Compose와 CI 정의 구현**. [호스팅 조사](hosting-guide.md)의 단일 서버 권고를 실제 작업 순서로 풀었다. 실제 분석의 영속 worker 연결과 공개 배포·CD는 미완료다. 현재 구현·명령은 [서비스 가이드](AGENTS.md)와 [실행 안내](../../service/README.md)를 따르며, 아래 초기 순서와 운영 제안을 모두 구현 사실로 읽지 않는다.

## 1. 작업을 세 단계로 나눈다

| 단계 | 완료 시 사용자가 할 수 있는 일 | 다음 단계로 넘어갈 증거 |
|---|---|---|
| A. 로컬 서비스 | 내 PC에서 입력 접수→진행→결과·실패·만료를 확인 | API·worker 재시작, 세션 분리, 모의 데이터 표시 검증 |
| B. 실제 분석 연결 | 공개 자료를 분석하고 실제 구조·근거를 조회 | 로직 adapter 검증, 실제 외부 호출, CPU·RAM·용량 측정 |
| C. 인터넷 배포 | 다른 PC에서 HTTPS로 같은 흐름 이용 | AWS 비용·권한·저장·TLS·장애·만료 검증 |

A와 로직 담당의 B 준비는 독립적으로 진행 가능하다. C의 mock 배포 점검도 가능하지만 실제 분석 서비스의 공개 완료는 B와 공급자 조건·실행 한도 확인이 필요하다. 이 순서는 배포 문제와 분석 문제를 각각 진단하기 위한 것이다.

## 2. 먼저 만들 백엔드의 범위

HTTP·필드·상태의 개발 기준은 [임시 계약 v0.1.0](temporary-contract.md)과 [JSON Schema](contracts/service.schema.json)다. 기존 계약을 새 문서에서 다른 이름으로 재정의하지 않는다.

| 구성 | 구현할 책임 | 첫 완료 기준 |
|---|---|---|
| 설정·DB migration | DB 접속, 서버 실행 모드, 세션·작업·파일 메타데이터와 버전 관리 | 빈 DB에서 재현 가능하게 준비, 잘못된 설정이면 시작 실패 |
| 세션 API | 서버 cookie 발급, heartbeat, 만료·삭제 요청 | 새로고침 복구·다른 세션 거부·만료 세션 부활 금지 |
| 입력 API | multipart·manifest·서열 형식·파일 크기·출처 확인 항목 | 실패 입력은 실행 큐에 들어가지 않음 |
| 실행 API | 실행 접수, request_key 중복 방지, 상태·결과·파일 조회 | 같은 접수 키가 새 분석·외부 호출을 만들지 않음 |
| worker 운영부 | 작업 점유·생존 확인·진행 기록·결과 등록 | API와 별도 프로세스에서 실행, worker 소실은 interrupted |
| logic adapter | LogicRequest·ProgressUpdate·LogicOutput 변환 | 모의 시나리오 후 실제 로직 연결, 모드·ID·단위·파일 검증 |
| 자료 정리 | 접근 만료와 안전한 파일·DB 삭제, 재시작 후 재처리 | 실행 중인 파일을 먼저 삭제하지 않으며 만료 자료를 공개하지 않음 |

처음부터 관리 화면·계정 가입·결제·분산 큐를 추가하지 않는다. 다만 공개 사용 시 전체 접수량과 외부 호출량 제한은 기존 PRD의 필수 운영 범위다.

### 백엔드에서 빠뜨리기 쉬운 연결

실행 접수는 DB 고유 제약과 트랜잭션으로 중복을 막는다. worker 점유는 짧은 트랜잭션으로 끝내고 분석 중 DB 잠금을 계속 잡지 않는다. lease·heartbeat와 현재 점유자의 결과 쓰기 권한을 연결하여 중단된 옛 worker가 결과를 덮어쓰지 않게 한다. 외부 호출은 exactly-once를 보장한다고 하지 않으며, timeout 시 외부 요청 ID로 조회 가능한지 먼저 판단한다. [현재 복구 설계](../ARCHITECTURE.md)

서버가 배정한 작업 디렉터리에 파일을 쓰고 완성된 파일의 크기·해시를 확인한 뒤 DB 참조를 등록한다. 파일 쓰기와 DB commit은 한 트랜잭션이 아니므로 고아 파일·참조 누락을 재시작 때 탐지한다. 같은 볼륨 안의 임시→최종 이동을 사용하고 사용자 파일명을 경로로 사용하지 않는다.

입력·결과·다운로드는 모두 세션 소유권을 검사한다. 공개된 run_id나 artifact_id를 아는 것만으로 조회를 허용하지 않는다. 임시 결과는 Caddy 정적 디렉터리에 두지 않으며 API 권한 검사를 통과해서만 제공한다. 공개 예제 구조와 사용자별 결과 구조를 별개 경로로 관리한다.

세션 정리는 긴 분석 실행과 독립된 주기로 동작해야 한다. 초기 제안은 API의 가벼운 정리 조정 루프가 DB에서 만료를 기록하고, worker가 안전한 중단 지점과 파일 사용 종료를 알린 뒤 정리를 완료하는 방식이다. API가 여러 프로세스로 확장되면 DB 잠금으로 정리 실행자를 조정한다. 구체적 주기·삭제 기한은 아직 확정하지 않는다.

## 3. Docker 학습과 준비 순서

먼저 이미지·컨테이너·볼륨의 차이를 확인하고, 서비스 프로세스 하나를 이미지로 실행한 뒤 네 서비스를 Compose로 연결한다. 설치된 Docker가 응답하므로 이 작업에서는 재설치를 하지 않았다.

| 순서 | 앞으로 준비할 산출물 | 이해해야 하는 점 |
|---|---|---|
| 1 | Python 의존성 파일·lockfile, API·worker 실행 명령 | 코드뿐 아니라 시스템 라이브러리·Python 버전도 실행 환경의 일부 |
| 2 | Python Dockerfile | API와 worker는 같은 이미지에서 다른 명령을 실행할 수 있음 |
| 3 | 웹 Dockerfile | Node로 Vite를 빌드한 뒤 Caddy 이미지에는 정적 결과만 넣음 |
| 4 | `.dockerignore`, 값 없는 설정 예시 | `.env`·Git 메타데이터·로컬 node_modules·분석 입력·결과가 이미지에 들어가지 않게 함 |
| 5 | Compose 개발 설정과 운영 차이 | 네트워크·볼륨·비밀값·재시작 정책·healthcheck를 함께 정의 |

이번 main의 프런트는 소스에서 `docs/frontend-hosting/fixtures` 타입을 참조한다. 웹 이미지의 빌드 context를 `frontend/`로만 제한하면 필요한 외부 경로가 빠질 수 있으므로, 첫 빌드는 저장소 루트 context와 선택적 COPY를 검토한다. 실제 빌드로 확인하기 전 Dockerfile을 확정하지 않는다.

Apple Silicon Mac은 arm64이고 제안 EC2는 amd64(x86_64)다. Mac에서 실행됐다고 x86 서버 호환성을 검증한 것은 아니다. 운영 이미지는 `linux/amd64` 대상 빌드와 해당 CPU에서의 분석 패키지 실행을 확인한다. 에뮬레이션 빌드 시간은 실제 서버 계산 성능의 근거로 사용하지 않는다. [Docker 멀티 플랫폼](https://docs.docker.com/build/building/multi-platform/)

### 네 컨테이너의 연결과 저장

| 서비스 | 네트워크 | 영속 데이터 | 비밀값 |
|---|---|---|---|
| web | 호스트 80/443 공개, 내부 api 접근 | Caddy 인증서·상태 | 모델 키 없음 |
| api | Compose 내부 8000 제안, 호스트 publish 없음 | 검증한 업로드·조회 파일 | DB 자격 증명 등 필요한 값만 |
| worker | 외부 수신 포트 없음, DB·외부 HTTPS 접근 | 작업 중간 파일·완성 파일 | DB·해당 모델 공급자 키 |
| db | Compose 내부 5432, 호스트 publish 없음 | PostgreSQL 데이터 | DB 비밀번호 |

컨테이너 안의 `localhost`는 그 컨테이너 자신이다. API가 DB에 연결할 때는 Compose의 `db` 서비스 이름을 사용한다. FastAPI는 컨테이너 내부에서 요청을 받을 수 있도록 listen 주소를 설정하되, 호스트에 8000을 공개할 이유는 없다.

`depends_on`만으로 DB 준비 완료가 보장되지 않는다. DB healthcheck → 한 번 실행하는 migration → API·worker 시작 순서를 만들고, 실행 중 DB 연결 끊김도 처리한다. 컨테이너 `healthy` 표시만으로 실패한 프로세스가 자동 재시작된다고 생각하지 않는다. 재시작 정책은 프로세스 종료와 함께 검증한다. [Compose 시작 순서](https://docs.docker.com/compose/how-tos/startup-order/)

운영 설정에서는 소스 bind mount·자동 reload를 제거하고 고정 이미지 버전을 사용한다. 로그 크기·보관 개수와 디스크 경고를 설정하여 로그가 DB 공간을 소진하지 않게 한다. 삭제·재시작을 배우는 과정에서 `down -v`나 volume prune을 일반 배포 절차로 사용하지 않는다. [Docker 운영 설정](https://docs.docker.com/compose/how-tos/production/), [볼륨 수명](https://docs.docker.com/engine/storage/volumes/)

Compose secrets는 서비스별로 파일을 전달하는 수단이며 AWS의 비밀 관리 서비스와 동일한 보관·회전 시스템은 아니다. 초기에는 서버의 제한된 파일에서 런타임에 주입하고, 실제 값은 저장소·이미지·명령 기록·프런트 번들에 넣지 않는다. `VITE_` 설정에 모델 키를 넣지 않는다. [Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/)

## 4. AWS를 만들기 전에 통과할 로컬 검사

| 시나리오 | 기대 동작 | 증거 |
|---|---|---|
| 정상 모의 접수 | 세션→입력→실행→상태→결과, mock 표시 유지 | HTTP 응답·화면의 같은 실행 ID |
| 중복 시작 클릭 | 동일 request_key는 같은 run 반환 | DB 실행 수와 adapter 호출 수 |
| API 재시작 | 기존 접수·결과 유지, 진행 조회 재연결 | 재시작 전후 ID·상태 비교 |
| worker 종료 | 성공으로 바뀌지 않고 interrupted로 확인 | 생존 만료·점유 정보, 자동 중복 호출 없음 |
| 2개 세션 | 서로의 상태·결과·구조·다운로드 거부 | 다른 세션에서 API 404 등 계약 응답 |
| heartbeat 중단 | 유예 내 복구, 만료 후 접근 차단 | 시각·응답·정리 상태 |
| 실행 중 만료 | 새 외부 호출 중지와 파일 정리 조정 | 실행·접근·삭제 상태를 별도로 확인 |
| 입력·파일 실패 | 큰 입력·파싱 실패·경로 이탈을 거부 | 실패 후 큐·파일·DB 잔여 상태 |
| 외부 timeout 모의 | 불명확한 호출을 즉시 재전송하지 않음 | 외부 요청 ID·check_run 안내 |
| 배포 교체 | 컨테이너를 바꿔도 유효 기간 내 자료 유지 | 볼륨 위치·파일 해시·결과 참조 |

그 뒤 실제 로직을 연결해 [D6 인계 목록](hosting-requirements.md)의 버전·시스템 라이브러리·실행 명령·CPU·메모리·디스크·호출량을 받는다. 단순 mock의 부하로 실제 예측 경로의 서버 크기를 확정하지 않는다.

## 5. AWS 계정부터 HTTPS까지의 순서

아래는 **EC2 기준 준비 절차**다. 아직 계정·예산·도메인이 확인되지 않았으므로 콘솔에서 그대로 실행 완료한 기록은 아니다. Lightsail을 선택하면 서버·방화벽·고정 IP 단계만 해당 상품 방식으로 바꾸고 서비스 검증은 유지한다.

### 5.1 계정·예산·운영 기간

AWS 계정 소유자와 결제 주체, 총 예산, 사용할 리전, 결과 발표일과 종료 판단일을 정한다. 루트 계정에는 MFA를 적용하고 일상 작업에는 필요한 권한을 가진 별도 접근을 사용한다. EC2가 AWS API를 사용할 때는 가능하면 인스턴스 역할의 임시 자격 증명을 사용한다. [IAM 권고](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)

월별·프로젝트 기간 예산 알림을 구성하되 AWS 사용료와 외부 모델 요금을 따로 추적한다. 무료 크레딧은 계정에서 적용 대상·잔액·만료를 확인하기 전 예산에서 빼지 않는다. 초기 자원에는 프로젝트·담당·종료 예정일 태그를 붙여 종료 시 찾을 수 있게 한다.

**완료 기준:** 총비용 계산표와 계정 권한·예산 알림·종료 일정이 준비됨. 알림만으로 강제 과금 상한을 보장하지 않음.

### 5.2 서버·네트워크·디스크

초기 제안은 서울의 Ubuntu 24.04 LTS amd64, 단일 On-Demand EC2, gp3 EBS다. 인스턴스 종류는 [실측·비용 판단](hosting-guide.md)을 거쳐 확정한다. 기존 4 vCPU·16 GiB는 첫 부하 검증 후보이며 무조건 필요한 최소 사양이 아니다.

단일 공개 서버는 인터넷 게이트웨이로 나가는 경로가 있는 public subnet과 공인 주소를 사용한다. 보안 그룹은 웹용 TCP 80·443만 전체 공개하고 DB 5432·API 8000·Docker daemon 포트는 공개하지 않는다. 이 구성의 외부 API 호출에 NAT Gateway를 추가할 필요는 없다. private subnet으로 바꾸면 egress 경로·비용을 별도로 설계해야 한다. [보안 그룹 규칙](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html)

관리 접속은 SSM Session Manager를 우선 검토한다. 이를 사용하려면 SSM Agent, 인스턴스 역할 권한, 서비스에 도달하는 통신이 필요하며 설정 없이 자동 접속되는 것은 아니다. SSH를 쓰는 경우에는 22를 관리자 IP에 한정하고 키를 보관한다. [Session Manager 연결](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connect-with-systems-manager-session-manager.html), [설정 선행 조건](https://docs.aws.amazon.com/en_en/systems-manager/latest/userguide/session-manager-getting-started.html)

EBS는 암호화하고 루트 디스크와 데이터 디스크의 역할을 기록한다. 용량은 이미지·빌드 임시 공간·DB·작업 최대치·로그의 합에 여유를 더해 결정한다. 별도 데이터 디스크를 쓰면 마운트 지점을 고정하고, 재부팅 후 그 마운트가 확인되어야 Compose를 시작한다. 마운트 실패 상태에서 같은 경로에 빈 DB를 새로 만들지 않게 한다. Docker named volume도 기본 저장 위치를 모르면 별도 EBS에 자동으로 저장되지 않는다.

EC2 종료 시 볼륨 삭제 설정과 남길 볼륨을 명시적으로 확인한다. Docker 볼륨 존속, EC2 중지, EC2 종료, EBS 삭제는 서로 다른 동작이다.

**완료 기준:** 관리자 접속 성공, 외부에는 의도한 포트만 열림, 재부팅 뒤 데이터 디스크·권한·여유 공간 확인.

### 5.3 Docker 설치·이미지 전달

선택한 Ubuntu 버전에 맞는 Docker 공식 apt 설치 절차로 Engine과 Compose plugin을 준비한다. 일반 사용자의 Docker socket 접근은 호스트에 강한 권한을 주므로 운영 담당으로 제한한다. Docker 서비스가 부팅 시 시작하는지 확인한다. [Ubuntu 설치](https://docs.docker.com/engine/install/ubuntu/)

첫 배포 준비는 검증한 커밋으로 amd64 이미지를 만들고 버전 태그·digest를 기록하는 것이다. 운영 서버에서 소스를 직접 빌드할 수도 있지만 메모리·시간·의존성 변동이 생긴다. 기본 권고는 빌드 환경에서 만든 이미지를 레지스트리로 전달하고 서버는 같은 digest를 실행하는 방식이다. 레지스트리 업로드와 Git push는 실제 구현 단계의 별도 작업이며 이번 조사에서 수행하지 않았다.

서버의 제한된 디렉터리에 Compose 설정과 필요한 비밀값을 배치하고, 이미지에는 비밀값을 포함하지 않는다. DB 비밀번호·공급자 키를 브라우저나 팀 문서에 옮기지 않는다. 로컬 `.env`를 서버로 통째로 복사하는 방식으로 필요한 설정을 추측하지 않는다.

**완료 기준:** 서버에서 필요한 이미지 pull, CPU 아키텍처 일치, 비밀값을 표시하지 않는 설정 검사, DB→migration→서비스 시작.

### 5.4 도메인·HTTPS·프런트 연결

도메인 또는 보유 도메인의 서브도메인을 준비하고, A 레코드를 고정 공인 IPv4로 연결한다. EC2의 일반 공인 IP는 중지·시작 후 바뀔 수 있어 Elastic IP를 검토한다. 이 주소는 사용·미사용 상태 모두 과금될 수 있다. IPv6를 설정하지 않았다면 잘못된 AAAA 레코드를 만들지 않는다. [EC2 주소 변화](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Stop_Start.html), [IPv4 가격](https://aws.amazon.com/vpc/pricing/)

Caddy에 도메인을 설정하고 80·443 도달성과 쓰기 가능한 영속 인증서 디렉터리를 확인한다. 공개 도메인의 자동 인증서 발급·갱신을 실제 브라우저에서 검증한다. IP로 접속해 나온 화면만으로 공개 HTTPS 완료라 하지 않는다. [Caddy 자동 HTTPS](https://caddyserver.com/docs/automatic-https)

Caddy는 `/api/*`를 FastAPI로 전달하고 다른 경로에서 Vite 정적 빌드를 제공한다. API의 404를 SPA의 `index.html`로 바꾸지 않도록 API 경로를 우선 분리한다. 초기에는 같은 도메인에서 프런트·API를 제공하여 임시 cookie 계약을 유지한다. 별도 프런트 호스팅으로 바꾸면 cookie 범위·CORS·Origin 검증을 다시 설계한다.

운영 cookie는 HttpOnly·Secure·SameSite와 변경 요청 Origin 검증을 적용한다. 사용자별 결과·파일 응답은 공유 캐시가 저장하지 않도록 하고, 공개 정적 자산과 같은 캐시 규칙을 적용하지 않는다. 이 부분은 [임시 계약](temporary-contract.md)의 소유권·만료 동작과 함께 검증한다.

**완료 기준:** 다른 네트워크의 PC에서 유효한 HTTPS·새로고침·세션 유지·API 오류·권한 있는 구조 다운로드 확인.

### 5.5 mock에서 live로 전환

우선 외부 모델을 호출하지 않는 모의 흐름으로 운영 서버의 접수·상태·만료·장애를 확인한다. 이후 실제 공개 입력 한 건과 해당 공급자 한도로 live 실행을 검증한다. `data_mode`는 서버 설정으로 결정하고 브라우저에서 임의 선택·승격하지 못하게 한다.

서비스 동시 실행은 기존 설계대로 worker 한 작업부터 시작한다. 공개 접수 전에 입력 바이트·서열·원자 수·대기 수·실행 시간·호출 횟수의 상한을 설정하고, 넘으면 계약의 413·429 등으로 설명한다. 글로벌 접수 차단과 live 호출 차단은 운영자가 즉시 적용할 수 있어야 한다. 구체적 숫자는 실제 입력과 quota를 측정한 뒤 정한다.

**완료 기준:** 같은 실행의 구조·근거·JSON·CSV가 일치하고, 실패·보류·부분 결과가 실제 상태대로 표시되며 비용·자원 한도 안에서 완료.

## 6. 배포 이후 업데이트·장애·종료

### 업데이트와 되돌리기

첫 버전은 짧은 점검 시간을 허용한다. 접수를 일시 중지하고 실행 중인 작업을 완료시키거나 중단 상태로 정리한 뒤, 이전 이미지 digest와 DB migration 버전을 기록한다. 준비된 새 이미지로 교체하고 readiness·기존 세션·새 작업을 확인한 후 접수를 재개한다. 배포 때문에 진행 중 외부 요청을 아무 기록 없이 재발송하지 않는다.

문제가 생기면 이전 이미지로 되돌리되 DB 스키마가 이전 코드와 호환되는지 먼저 확인한다. 이미지 되돌리기만으로 파괴적 DB migration이 취소되지 않는다. 초기 migration은 이전 코드와 호환되는 변경을 우선하고, DB·파일 복원은 별도 검증한 절차를 사용한다.

임시 사용자 결과를 전체 서버 스냅샷에 자동으로 무기한 보관하지 않는다. 코드·이미지·재현 가능한 공개 예제와 사용자 임시 데이터를 구분해 백업 범위를 정한다. 복원 시 만료된 세션·결과가 다시 노출되지 않아야 한다. 임시 데이터 백업을 제외하면 호스트 유실 시 그 세션을 복구하지 못하는 한계도 함께 수용해야 한다. [ADR-008](../ADR.md)

### 자주 마주칠 증상

| 증상 | 먼저 확인할 위치 | 판단 |
|---|---|---|
| 사이트 자체가 안 열림 | DNS→공인 IP→보안 그룹→Caddy | 앱 분석 오류와 네트워크 장애를 분리 |
| HTTPS 인증서 실패 | DNS·80/443·인증서 디렉터리·Caddy 로그 | 발급 재시도를 반복하기 전에 원인 확인 |
| 502·API 준비 실패 | api 상태·listen 주소·DB·migration | Caddy가 실행돼도 API가 준비됐다는 뜻은 아님 |
| queued에서 멈춤 | worker 생존·DB 점유·접수 한도 | 새 실행을 계속 만들지 않음 |
| running 중단·OOM | worker 로그·메모리·호스트·공급자 요청 상태 | 성공 여부 불명확한 외부 호출의 자동 반복 금지 |
| DB 쓰기·파일 저장 실패 | 디스크·inode·권한·데이터 마운트 | 새 작업 접수를 줄이고 기존 데이터 보존 |
| 구조 파일 403/404·만료 | 세션·artifact 소유권·파일 완성·수명 | 모든 구조를 공개 경로로 옮겨 우회하지 않음 |

API readiness는 필요한 DB·스키마·저장소를 확인하되 외부 유료 모델 호출을 healthcheck로 실행하지 않는다. worker 생존은 HTTP 포트 대신 기록된 heartbeat로 확인할 수 있다. 운영 로그에는 실행 ID·단계·시간·오류 코드만 필요한 만큼 남기고 서열·cookie·키·전체 모델 응답은 기본 로그에 넣지 않는다.

### 서비스 종료

결과 발표 후 종료 조건이 충족되면 새 실행을 막고 진행 중 작업·외부 호출을 정리한다. 허용된 결과 인계와 임시 자료 삭제를 마친 뒤 서버뿐 아니라 남은 EBS·스냅샷·Elastic IP·레지스트리 이미지·로그·DNS·도메인 자동 갱신을 확인한다. 계정 청구 화면에서 잔여 과금 자원을 확인해야 종료가 끝난다. 실제 삭제는 그 시점의 보관 결정에 따라 수행한다.

Lightsail을 선택했다면 중지로 과금이 끝나지 않는 점을 다시 확인한다. EC2도 서버 중지만으로 전체 과금이 0이 되지 않는다. [Lightsail FAQ](https://aws.amazon.com/lightsail/faq/), [EC2 중지·시작](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Stop_Start.html)

## 7. 다음 구현 작업의 순서와 인계

| 순서 | 서비스 담당의 작업 | 로직·프런트와 맞출 내용 | 완료 증거 |
|---|---|---|---|
| 1 — 로컬 구현 | FastAPI·DB·세션·입력·실행 접수 API | v0.1.0 오류·cookie·ID, 프런트 service client | 정상·오류·다른 세션 접근과 API 재시작 뒤 조회 검사 |
| 2 — 로컬 검증 완료 | Dockerfile·Compose·Caddy의 로컬 배포 뼈대 | 프런트 빌드 context, 현재 API·DB 의존성, worker의 후속 연결 위치 | web·api·db 기동, DB 준비·migration 순서, 컨테이너 교체 후 접수 조회와 파일 유지 |
| 3 — 구현됨 | mock worker·점유·heartbeat·결과·정리 | 정상/보류/부분 실패/중단/만료 표시 | 별도 프로세스의 재시작·중복 방지·수명 검사 |
| 4 — 구현됨 | worker와 화면을 Compose 환경에 연결 | 같은 실행의 상태·결과와 mock 표시 | web·api·worker·db 전체 mock 흐름과 재기동 검사 |
| 5 | 실제 logic adapter·파일 검증 | 실제 진입 함수·단계·파일·잔기·정렬 규약 | 실제 공개 입력 한 건, 자원·호출량 측정 |
| 6 | 비용·계정·도메인 확정과 AWS 배포 | 운영 기간, 공급자 접근·공개 실행 조건 | HTTPS·실제 결과·장애·만료·재배포 검증 |

2026-09-26 사용자 결정으로 2의 뼈대를 worker 완성 전에 먼저 준비했다. 당시 2의 검증 범위는 접수·저장까지였고 이후 3–4의 mock worker·화면 연결이 구현됐다. 5의 실제 분석 연결은 별도 작업이다. 예산·계정·도메인·정확한 운영 날짜는 자원 생성 전 사용자 결정이 필요하다. 실제 CPU·RAM·모델 응답 시간은 사용자에게 추측하도록 묻지 않고 로직 실행으로 측정한다.

## 8. CI/CD 도입 계획

추가 조사일: 2026-09-26. **GitHub Actions로 CI는 자동 실행하고 CD는 배포 버튼으로 시작하는 방식**을 제안한다. 현재 [integration.yml](../../.github/workflows/integration.yml)은 PR·main의 빌드·계약·서비스·Compose mock 검사를 정의한다. 이 update에서는 원격 실행 성공을 재검증하지 않았다. 아래 ECR 이미지 보관·AWS 권한·배포 스크립트·CD는 여전히 계획이다.

CI는 코드 변경 때마다 빌드·검사를 자동으로 실행하는 과정이다. CD는 검사한 버전을 배포 가능한 상태로 준비하고 서버에 반영하는 과정이며, 초기에는 사람이 배포 시점을 선택하는 continuous delivery로 운영한다. 해커톤 시연이나 긴 분석 실행 중 서버가 예고 없이 교체되지 않게 하기 위한 선택이다.

### 언제 무엇을 자동화하는가

| 시점 | 자동 수행할 작업 | 완료 기준 |
|---|---|---|
| PR 생성·수정 | 프런트 의존성 설치·타입 검사·빌드, 임시 계약 검증 | 실패한 검사를 PR에서 확인 가능. 필수 검사 설정은 저장소 권한·플랜 확인 후 적용 |
| 백엔드·Docker 구현 이후의 PR | 백엔드 테스트, 임시 PostgreSQL을 사용한 연동 검사, amd64 이미지 빌드·mock Compose 검사 추가 | 세션 분리·중복 접수·worker 중단·만료와 기동 검증 통과 |
| main 병합 | 병합된 커밋을 다시 검사하고 운영 이미지를 빌드해 ECR에 보관 | 정확한 commit SHA와 이미지 digest의 대응 기록 |
| 배포 버튼 실행 | 성공한 main 빌드의 버전 선택, 서버에 배포 명령 전달, 교체 후 검증 | 배포 스크립트 종료와 실제 서비스 확인까지 성공 |

일반 CI는 외부 모델을 호출하지 않고 mock·고정된 공개 입력으로 검사한다. 실제 모델 호출은 한도와 비용을 정한 별도 수동 통합 검사로 분리한다. 과학적 계산 검증과 HTTP·작업 상태 검증도 구분하며, 합성 시나리오 통과를 실제 분석 성능으로 기록하지 않는다.

프런트는 기존 `npm run build`, 계약은 기존 `validate-contract.py`를 출발점으로 사용한다. Node·Python·의존성 버전은 lockfile과 검증한 실행 환경으로 고정한다. 백엔드 코드와 Dockerfile이 생기기 전 존재하지 않는 테스트를 통과 처리하지 않는다. PR의 코드는 운영 자격 증명 없이 GitHub-hosted runner에서 검사하고, 운영 EC2를 PR용 runner로 사용하지 않는다.

### 이미지 준비와 배포를 분리한다

| 구성 | 역할 | 제안 경계 |
|---|---|---|
| GitHub Actions | 검사·이미지 빌드·배포 시작 | 운영 배포는 수동 `workflow_dispatch`, 선택 버전의 main 소속·빌드 성공을 검증 |
| ECR | AWS의 Docker 이미지 보관소 | 웹 이미지와 API/worker 이미지를 버전별 저장. 배포는 변경 가능한 latest 대신 digest로 고정 |
| GitHub OIDC·AWS IAM | workflow에 임시 AWS 권한 발급 | 이미지 게시와 운영 배포 역할을 분리하고 저장소·허용 branch/environment와 필요한 자원으로 제한 |
| EC2 인스턴스 역할 | 서버가 ECR 이미지를 받고 SSM을 사용 | GitHub 빌드 권한과 별개로 필요한 pull·관리 권한만 부여 |
| SSM Run Command | 관리 대상으로 설정한 EC2에서 배포 스크립트 실행 | 대상 인스턴스·허용 명령을 제한하고 완료 상태·종료 코드를 확인 |

ECR은 이미지 저장소이고 SSM은 서버에 명령을 전달하는 기능이다. 둘 다 worker 작업 정리나 DB migration을 대신하지 않으므로 그 순서는 배포 스크립트로 구현한다. SSM 명령 접수 성공만으로 배포 성공을 표시하지 않고 실행 종료와 HTTPS·API 검증까지 기다린다. [ECR 이미지 조회·pull](https://docs.aws.amazon.com/AmazonECR/latest/userguide/docker-pull-ecr-image.html), [SSM Run Command](https://docs.aws.amazon.com/systems-manager/latest/userguide/run-command.html)

OIDC는 장기 AWS access key를 GitHub secret에 저장하지 않고 임시 권한을 받는 방식이다. 신뢰 정책의 `aud`·`sub`는 실제 저장소의 claim 형식에 맞추고 무관한 저장소·PR에 배포 권한을 주지 않는다. Environment를 쓰면 subject 형식도 달라질 수 있으므로 branch 기반 예제를 그대로 복사하지 않는다. 모델 키·DB 비밀번호는 서버 런타임에만 두고 이미지 빌드 인수나 로그에 넣지 않는다. [GitHub의 AWS OIDC 설정](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)

GitHub의 배포 버튼과 Environment의 필수 승인자는 서로 다른 기능이다. 처음에는 배포 버튼으로 시작하고, 필수 승인자 기능은 저장소 공개 여부·GitHub 플랜에서 지원되는지 확인한 뒤 사용한다. 버튼 실행도 자동 배포 권한을 가진 임의 branch를 허용한다는 뜻은 아니다. [Workflow 트리거](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow), [Environment 지원 조건](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)

이 OIDC·ECR·SSM 조합은 **EC2를 선택했을 때의 제안**이다. Lightsail을 선택하면 서버 관리 접속·인증 경로를 별도로 확인하고 CD 전달 단계를 조정하며, EC2 인스턴스 역할·SSM 구성이 그대로 제공된다고 가정하지 않는다.

### 배포 스크립트가 지킬 순서

1. **대상 확인:** 성공한 main 빌드의 웹·API/worker 이미지 digest, 설정·migration 버전, 대상 서버를 확정하고 이전 배포 정보를 보존한다.
2. **중복 배포 방지·작업 정리:** 운영 배포는 한 번에 하나만 실행하고 새 배포 요청이 진행 중 교체를 강제 취소하지 않게 한다. 신규 접수와 worker의 새 작업 점유를 멈추고 기존 작업을 기다리거나 기록을 남겨 안전하게 중단한다. 정해진 대기 시간을 넘으면 배포를 중단하고 상태를 알린다.
3. **교체:** 확인한 이미지를 pull하고 DB 변경 호환성을 확인한 뒤 migration·Compose 갱신을 수행한다. 볼륨을 삭제하지 않으며 여러 서비스의 이미지는 같은 배포 기록으로 관리한다.
4. **검증·접수 재개:** 컨테이너 readiness, worker 생존, HTTPS·세션·상태·권한 있는 파일 조회를 확인하고 접수를 재개한다. 기본 배포 검사는 유료 예측을 실행하지 않는다.
5. **실패 처리:** 실패 단계·실행 버전을 남기고 DB와 호환될 때만 이전 이미지로 복귀한다. migration이 이전 코드와 호환되지 않으면 자동 복귀를 멈추고 점검 상태를 유지한다.

이는 단일 서버의 점검 배포이며 무중단 배포를 보장하지 않는다. 재배포로 외부 모델 호출을 중복시키거나 만료된 자료를 복원해서 노출하지 않아야 하며, 상세 복구·보관 경계는 위 6절을 따른다.

### 도입 순서와 완료 증거

| 단계 | 도입할 범위 | 검증할 것 |
|---|---|---|
| 지금 | 프런트 빌드·계약 검증 CI | 정상 PR 통과, 의도적으로 잘못된 입력·타입은 실패 |
| 백엔드·Docker 준비 후 | 백엔드·DB·mock Compose 검사와 main 이미지 게시 | 코드 변경으로 실패를 검출, 게시 이미지와 검사한 커밋의 대응 |
| AWS 첫 배포 후 | 수동 CD·배포 기록·복귀 | 선택 digest 배포, 중복 배포 차단, 진행 작업 보호, 교체 실패·DB 호환성 처리 |

CI/CD 비용에는 GitHub runner 실행 시간·artifact/cache 보관과 ECR 이미지 저장·전송이 추가된다. 실제 저장소 플랜의 포함량과 AWS 요율을 확인하기 전 무료로 가정하지 않는다. 오래된 이미지는 보관 정책으로 정리하되 현재 운영·복귀 대상 digest는 남긴다. main 병합 즉시 운영 자동 배포는 위 경로가 안정된 뒤 별도로 결정한다.

## 9. 이번 조사에서 실제 확인한 범위

main 기준 코드·설계·임시 계약을 대조하고, 공식 AWS·Docker·Caddy·FastAPI·Render·NVIDIA 문서를 조회했다. 별도 작업 워크트리를 만들었고 로컬 Docker CLI·Compose·daemon 응답을 확인했다. 후속 CI/CD 조사에서는 GitHub 공식 workflow·OIDC·Environment 문서와 AWS ECR·SSM 문서를 확인했다. 조사 문서와 영역 가이드의 상대 링크 대상·공백 오류를 검사했다.

새 FastAPI 코드·Dockerfile·Compose·GitHub Actions workflow를 구현하거나 컨테이너를 배포하지 않았다. AWS 계정·권한·크레딧·실제 인스턴스 가용성, 모델 호출·요금, 분석 패키지 호환성·실행 부하, HTTPS·복구·삭제 동작과 CI/CD 실행은 이후 검증 대상이다.
