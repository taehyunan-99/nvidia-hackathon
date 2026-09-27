# Bio-3 검토 화면

React·TypeScript·Vite 기반의 네 단계 검토 화면. 저장소 루트에서 `npm --prefix frontend ci`, `npm --prefix frontend run dev`로 실행한다. `npm --prefix frontend run build`는 타입 검사와 정적 빌드를 수행한다.

첫 화면은 테스트 데이터 선택과 직접 입력으로 나뉜다. 테스트 데이터는 가로 카드 3개로 선택하며 실험 구조와 예측 비교가 기본값이다. 직접 입력은 고정 HER2 표적과 후보 2–4개의 이름·중쇄·경쇄·선택 PDB 출처를 받는다. JSON 업로드와 저장 기록 애니메이션 다시보기는 제공하지 않는다.

Compose 빌드는 `VITE_PERSISTENT_SERVICE=1`, `VITE_API_BASE=''`로 같은 출처의 영속 API를 사용한다. 접수→worker→진행 조회→3D·보고서·파일·세션 재조회가 연결되어 있다. API가 반환한 mock/live를 구분하고 실제 실행 파일은 소유권을 확인하는 경로로 받는다. `npm run dev`만 실행한 별도 동기 시연 모드와 구별한다. 준비 입력·분석 한계는 [테스트 데이터](../docs/frontend-hosting/test-data.md), 서비스 실행은 [service/README.md](../service/README.md)를 따른다. 글꼴은 외부 CDN을 사용하며 실패 시 시스템 sans-serif로 표시된다.

저장된 실행의 입력은 한 번 조회하고, 대기·분석 중에는 응답 완료 후 2초 간격으로 상태를 확인한다. 완료·부분 완료·실패·중단 상태를 받으면 상태와 결과의 반복 조회를 멈추고 1분 간격으로 세션만 유지한다. 결과는 현재 화면 메모리에 보관하며 새로고침이나 실행 주소 변경 시 서버에서 다시 조회한다. 세션 만료·접근 거부는 계속 표시하고 해당 결과 화면을 해제한다. 조회 중복·완료 후 요청량·재조회·만료 회귀는 `node --experimental-strip-types --test frontend/tests/*.test.mjs`와 브라우저의 실제 요청 기록으로 확인한다.

설계 기준은 [디자인 가이드](../docs/frontend-hosting/design-guide.md), 화면과 제한은 [화면 계획](../docs/frontend-hosting/screen-plan.md)을 참고한다.
