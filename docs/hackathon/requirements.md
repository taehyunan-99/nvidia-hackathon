# 해커톤 요구사항: 확인된 사실과 미확인 사항

> 이전 기록: `nvidia/docs/01-hackathon-requirements.md`에서 2026-09-24 이관. 아래 조사·작성 기준일을 유지하며 이번 이관에서 외부 사실이나 실행 결과를 재검증하지 않았습니다.

기준일: 2026-09-22. 출처는 [패스트캠퍼스 공식 페이지](https://fastcampus.co.kr/NVIDIA_hackathon)와 해당 페이지에 게시된 안내 이미지다.

## 공식 확인

| 항목 | 확인 내용 | 근거 |
|---|---|---|
| 대회 | Korea Agentic AI Hackathon | 공식 페이지 |
| 지향점 | 목표를 받아 계획을 세우고 도구를 호출해 문제를 해결하는 에이전트 | 공식 페이지 본문 |
| 예선 | 9월 11~28일 온라인 사전 챌린지, 본선 10팀 선발 | 아래 Phase 1 이미지 |
| 예선 제출 | 미션 확인 후 NVIDIA Build의 Skill API를 활용한 에이전트 데모 | Phase 1 이미지 |
| 본선 | 10월 7일 오프라인 One Day Hackathon, 10팀 중 5팀 선발 | Phase 2 이미지 |
| 본선 미션 | 해커톤 당일 별도 안내, 사전 비공개 | Phase 2 이미지 |
| 쇼케이스 | 11월 9~10일 NVIDIA AI Day Seoul, 서울 코엑스, 상위 5팀 | Phase 3 이미지 |
| 우승 혜택 | DGX Spark 1대, 공식 GitHub Recipe 등재, 글로벌 기술 블로그·인터뷰 소개 | 우승 혜택 이미지 |
| 본선 자원 | 팀당 최대 USD 1,000 NVIDIA Brev 크레딧, L40S 1대 구성 표기 | 본선 혜택 이미지 |

행사 이미지에 표시된 연도는 2026년이다. 마감 시각·시간대는 공개 자료에서 확인하지 못했다.

## 직접 확인한 원본 이미지

- [Phase 1: 온라인 예선](https://cdn.day1company.io/prod/uploads/202609/153942-1931/%E1%84%80%E1%85%A2%E1%84%8B%E1%85%AD-01.webp)
- [Phase 2: 오프라인 본선](https://cdn.day1company.io/prod/uploads/202609/153945-1931/%E1%84%80%E1%85%A2%E1%84%8B%E1%85%AD-02.webp)
- [Phase 3: 최종 쇼케이스](https://cdn.day1company.io/prod/uploads/202609/132654-277/frame-2147239726.webp)
- [본선 10팀 혜택: Brev·L40S](https://cdn.day1company.io/prod/uploads/202609/132319-277/frame-2147239728.webp)

## 기술 조건을 해석할 때 주의할 부분

공개 페이지는 **DGX Spark, Nemotron, NIM, NemoClaw, OpenShell, L40S**를 명시한다.
하지만 이 여섯 가지를 전부 써야 한다는 문장은 확인되지 않았다.
또한 NVIDIA 전체 제품 목록을 대회 공식 허용 목록으로 볼 근거도 없다.
이 조사에서 NAT, cuOpt, Retriever, VSS 등을 포함한 것은 기술적으로 연결 가능한 후보이기 때문이다.

Phase 1 이미지의 짧은 원문은 **“Build NVIDIA의 Skill API”**다.
이 표현이 `NVIDIA/skills` 설치, Build 모델 API 호출, 지정 스킬/API 사용 중 무엇을 정확히 뜻하는지는 공개 페이지만으로 확정할 수 없다.
따라서 **특정 GitHub 스킬을 반드시 몇 개 설치해야 한다**고 단정하지 않는다.

## 신청서 접근 한계

페이지의 [공식 신청 링크](https://docs.google.com/forms/d/e/1FAIpQLScyZ5GYYaCOycNUzXVUTenliEUmSEIdXelVdYphvMvLeLuiHA/viewform)는 Google 로그인 화면으로 이동했다.
이 문서의 9월 22일 조사에서는 로그인 이후 질문을 확인하지 못했다. 다만 별도 9월 20일 조사에서는 공개 폼 정의를 확인해 [신청 폼 스냅샷](application-form.md)에 기록했다. 당시 팀장에게 서비스 파일 업로드와 문제·솔루션·기술 스택 입력이 요구됐고, URL 제출은 링크를 적은 문서를 업로드하도록 안내됐다. 실제 제출 시점의 필드·제한은 다시 확인해야 한다.

9월 20일 폼은 [NVIDIA 지정 교육](https://learn.nvidia.com/courses/course-detail?course_id=course-v1:DLI+S-FX-43+V1)을 안내했다. 강의 내용과 실습 경로는 [DLI 학습 노트](nemoclaw-course-notes.md)에 정리돼 있다. 폼 분석에서 수료증 업로드 질문은 확인되지 않았으므로 교육 이수·수료증 제출 의무는 단정하지 않는다.

## 규정 확인이 필요한 질문

1. 예선 미션의 전문과 허용 주제 범위는 무엇인가?
2. 데모 제출은 동영상·실행 URL·GitHub·파일 중 무엇이며, 각각 필수인가?
3. NVIDIA 모델·API·스킬 중 필수 항목과 최소 사용 범위는 무엇인가?
4. 외부 LLM, 일반 프레임워크, 외부 검색 API와 기존 코드 사용은 허용되는가?
5. 팀 인원·참가 자격·심사 배점·영상 길이·제출 마감 시각은 무엇인가?
6. 본선 Brev 크레딧의 지급 시점·기간·대상 비용·초과 비용 처리는 무엇인가?
7. 본선에서 예선 코드·인덱스·모델·사전 제작 도구를 재사용할 수 있는가?

## 준비 방향 — 분석

- **예선**: 지정 미션을 확인한 뒤 목표→도구 호출→결과 검증을 보여주는 좁은 데모를 준비한다.
- **본선**: 당일 다른 미션에 맞게 데이터·도구를 교체할 수 있는 실행 경험을 확보한다.
- **자원**: 예선은 개인 API 접근이나 보유 환경으로 시작할 수 있다고 가정하되, 지원 지급을 전제로 일정을 짜지 않는다.
- 구체적인 데모 수준 제안은 [데모 준비 기준](demo-readiness.md)에 별도로 정리했다.
