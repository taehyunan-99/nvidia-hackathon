# HER2 프런트 프로토타입

React·TypeScript·Vite 기반의 네 화면 디자인 검토용 앱. 저장소 루트에서 `npm --prefix frontend ci`, `npm --prefix frontend run dev`로 실행한다. `npm --prefix frontend run build`는 타입 검사와 정적 빌드를 수행한다.

`docs/frontend-hosting/fixtures/scenarios.json`의 9개 모의 상태를 사용한다. 실제 분석·구조·다운로드·서버·세션은 연결되지 않았다. 입력 UI는 전송하지 않으며 소개용 입체 그래픽은 분자 구조가 아니다. 글꼴은 외부 CDN을 사용하며 실패 시 시스템 sans-serif로 표시된다.

설계 기준은 [디자인 가이드](../docs/frontend-hosting/design-guide.md), 화면과 제한은 [화면 계획](../docs/frontend-hosting/screen-plan.md)을 참고한다.
