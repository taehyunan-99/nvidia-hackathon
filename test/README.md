# 업로드용 모의 시나리오

이 폴더의 JSON 파일 9개는 각각 하나의 검토 시나리오를 담는다. 파일 하나에 입력(`input`)과 순서대로 재생할 상태(`scenarios[]`)가 모두 있어, 이후 사이트의 파일 업로드에서 독립적으로 읽을 수 있다. 배열의 마지막 항목이 파일 이름에 해당하는 최종 상태다. 각 상태에는 세션·실행·결과·오류가 있으며, 진행 상태의 `run_id`는 파일 안에서 동일하게 맞췄다. 형식은 `docs/frontend-hosting/contracts/service.schema.json`의 `FixtureSet` v0.1.0이며 상태 내용의 원본은 `docs/frontend-hosting/fixtures/scenarios.json`이다.

모든 파일은 합성 자료(`data_mode: "mock"`)다. `completed`도 실제 분석·구조 계산·다운로드 파일 생성을 뜻하지 않는다. 사이트에서 파일을 업로드해 검토를 시작하면 기록이 자동으로 재생되고, 마지막 기록에 결과가 있을 때 비교·보고를 열 수 있다. 재생 간격은 화면 연출일 뿐 실제 계산 시간이나 완료 예측을 뜻하지 않는다. `input-invalid`는 합성 오류 응답의 재생이며 입력 데이터의 필수 필드를 제거한 예제는 아니다. 만료 시 이전 결과를 다시 노출하지 않는다.

파일별 의미: `queued` 대기, `running` 진행, `completed` 모의 완료, `scientific-hold` 판단 보류, `partial` 부분 결과, `failed` 실행 실패, `interrupted` 실행 중단, `session-expired` 세션 만료, `input-invalid` 입력 오류.
