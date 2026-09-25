# HER2 검토 화면

React·TypeScript·Vite 기반의 네 단계 검토 화면. 저장소 루트에서 `npm --prefix frontend ci`, `npm --prefix frontend run dev`로 실행한다. `npm --prefix frontend run build`는 타입 검사와 정적 빌드를 수행한다.

검토 입력에서 저장소 루트 `test/`의 JSON 파일 하나를 업로드하면 입력을 확인한 뒤 파일의 상태 기록이 순서대로 모의 재생된다. 마지막 기록에 결과가 있으면 구조 비교와 결과 보고로 이동할 수 있다. 파일은 브라우저에서만 읽으며 실제 분석·서버 세션·결과 다운로드는 연결되지 않았다. 비교 화면의 공개 구조 미리보기는 업로드한 후보의 계산 결과가 아니다. 글꼴은 외부 CDN을 사용하며 실패 시 시스템 sans-serif로 표시된다.

설계 기준은 [디자인 가이드](../docs/frontend-hosting/design-guide.md), 화면과 제한은 [화면 계획](../docs/frontend-hosting/screen-plan.md)을 참고한다.
