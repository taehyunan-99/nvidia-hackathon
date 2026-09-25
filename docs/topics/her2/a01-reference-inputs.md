# A-01 공개 구조 기준 입력 조사

확인일: 2026-09-26 KST. 작업 브랜치: `feat/structure-analysis`.
상태: **자료 확보·대응표 생성·기술 검증, 첫 분석 범위·최소 연결 규칙의 사용자 확인 완료. 실제 팀 연동·예측 검증은 별도 미완료**.
이 문서는 [계획 A-01](../../plan.md#5-로직-a-계획--자료와-구조-분석)의 조사 산출물이다. 최종 데모 후보 선정이나 A-02 계산 완료 기록은 아니다.

## 확인 결과

[1N8Z](https://www.rcsb.org/structure/1N8Z)는 HER2–trastuzumab(Herceptin) Fab,
[1S78](https://www.rcsb.org/structure/1S78)는 HER2–pertuzumab Fab의 실험 구조다.
두 구조의 원본 mmCIF와 공식 biological assembly 파일, [UniProt P04626 서열](https://www.uniprot.org/uniprotkb/P04626/entry)을 직접 확보해 대조했다.
항체 입력은 해당 PDB에 기탁된 Fab 서열이다. 전체 IgG 서열 또는 새로운 항체 후보를 생성한 것이 아니다.

| 항목 | 1N8Z | 1S78 |
|---|---|---|
| 실험 방법 / 해상도 | X-ray / 2.52 Å | X-ray / 3.25 Å |
| 원본 비대칭 단위의 단백질 사슬 | 3개 | 6개: 동일 후보의 복합체 2벌 |
| 기탁 / 좌표 있는 단백질 잔기 | 1,041 / 1,015 | 2,128 / 1,995 |
| 원본 원자 행 수 | 7,890 | 15,481 |
| HER2 기탁 서열의 UniProt 대응 | P04626 23–629 | P04626 23–646 |
| assembly | 1 | 1, 2 |

원본 파일의 주석·좌표에서 집계한 값이며, 기탁/관측 잔기 수와 원자 수는 RCSB entry의 수치와도 대조했다.
해상도와 관측 잔기 수는 후보의 결합력 순위가 아니다.

## 사슬·번호·누락

아래 단백질 사슬은 label/auth 사슬 ID가 같다. 길이와 누락 범위는 **기탁 서열 위치(label_seq_id)** 기준이고 양끝을 포함한다.

| 구조 / 사슬 | 역할 | 서열 길이 | 좌표 있는 잔기 | 좌표 없는 위치 |
|---|---|---:|---:|---|
| 1N8Z A | Fab 경쇄 | 214 | 214 | 없음 |
| 1N8Z B | Fab 중쇄 | 220 | 220 | 없음 |
| 1N8Z C | HER2 | 607 | 581 | 102–110, 303–305, 361–364, 581–590 |
| 1S78 A | HER2, assembly 1 | 624 | 555 | 102–110, 565–624 |
| 1S78 B | HER2, assembly 2 | 624 | 568 | 102–110, 578–624 |
| 1S78 C / E | Fab 경쇄, assembly 1 / 2 | 각각 214 | 각각 214 | 없음 |
| 1S78 D / F | Fab 중쇄, assembly 1 / 2 | 각각 226 | 각각 222 | 각각 223–226 |

1S78 중쇄 D/F에는 author 번호 `52A`, `82A`, `82B`, `82C`, `99A`, `99B`가 있다.
예를 들어 label 84는 author 82 + 삽입 코드 A이며, 누락 label 223–226은 author 217–220이다.
중쇄를 author 정수 번호만으로 연결하면 서로 다른 잔기를 합치므로, 사슬·번호·삽입 코드를 함께 사용한다.

HER2는 두 entry 모두 label/auth 번호 1이 UniProt 위치 23에 대응한다.
`_struct_ref_seq`의 대응 구간 전체를 실제 UniProt FASTA와 비교해 일치함을 확인했다.
입력 JSON의 표적 FASTA는 1,255개 잔기의 전체 P04626이므로, D2의 HER2 `sequence_position`은 **UniProt 위치**다.
항체 `sequence_position`은 입력에 넣은 기탁 Fab FASTA 위치이며, 두 번호 체계의 차이를 [bundle.json](assets/a01/generated/bundle.json)에 기록했다.
CSV와 chain-mapping JSON의 `entity_id`는 ASU 원본 기준이다. 공식 assembly 파일에서 entity 번호가 재배정될 수 있으므로, assembly 좌표 연결에는 검증된 label 사슬·잔기 identity를 사용한다.

좌표 있는 잔기는 `_atom_site`와 대조하고, 누락 잔기는 `_pdbx_poly_seq_scheme`와 `_pdbx_unobs_or_zero_occ_residues`를 교차 확인했다.
`_pdbx_poly_seq_scheme.auth_seq_num`은 좌표 레코드 번호와 다를 수 있어 별도 열로 보존했다.
author 좌표 번호에는 scheme의 `pdb_seq_num`을 사용하고 실제 `_atom_site.auth_seq_id`와 일치하는지 검사했다.
근거: [wwPDB auth_seq_num 정의](https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/Items/_pdbx_poly_seq_scheme.auth_seq_num.html), [pdb_seq_num 정의](https://mmcif.wwpdb.org/dictionaries/mmcif_pdbx_v50.dic/Items/_pdbx_poly_seq_scheme.pdb_seq_num.html).

## Assembly와 당쇄·주변 구조

| 파일 | 포함 label 사슬 | 원자 수 | 용도 |
|---|---|---:|---|
| 1N8Z assembly 1 | A,B,C,D,E,F,G,H,I | 7,890 | D1 계약 대조 예시 |
| 1S78 assembly 1 | A,C,D,G,H,L | 7,669 | D1 계약 대조 예시 |
| 1S78 assembly 2 | B,E,F,I,J,K,M | 7,812 | 동일 pertuzumab 후보의 대체 복합체 |

세 assembly의 operator 1은 항등 변환이다. 공식 assembly 파일의 원자 식별자·좌표·점유율·B factor가 원본에서 해당 사슬을 선택한 결과와 일치했다.
원본 좌표 단위는 Å이며 구조 간 중첩은 수행하지 않았다(`alignment: null`). Assembly 생성과 구조 간 정렬은 별도 작업이다.
D1은 각 assembly 1을 사용하며 2026-09-26 사용자가 이를 첫 분석 범위로 채택했다. 이는 품질 우열이나 최종 데모 선정을 뜻하지 않는다.
원본 1S78의 두 복합체를 하나의 항체 복합체로 섞거나 두 개의 서로 다른 후보로 세지 않는다.

| 구조 조건 | 좌표로 확보한 당 성분 | HER2에 연결된 위치: 구조 번호 → UniProt |
|---|---|---|
| 1N8Z assembly 1 | NAG 2개: label D,E | 165→187, 237→259 |
| 1S78 assembly 1 | NAG 5개: label G,H,L | 165→187, 237→259, 508→530 |
| 1S78 assembly 2 | NAG 7개 + BMA 1개: label I,J,K,M | 165→187, 237→259, 508→530, 549→571 |

당쇄와 단백질의 연결은 원본 `_struct_conn`의 공유결합 주석에서 확인했고 [summary.json](assets/a01/generated/summary.json)에 원래 필드를 보존했다.
비단백질 잔기의 `label_seq_id`는 null이다. 예를 들어 1N8Z의 NAG label D는 author 사슬 C, author 번호 766이므로 단백질 C의 서열 위치로 취급하지 않는다.
1N8Z의 황산 이온 1개와 물 79개도 원본 및 대응표에 보존했다. 계산에서의 포함·제외 기준은 A-02에서 결정한다.

현재 확보된 당은 관측된 일부 원자다. 전체 생리적 당쇄의 완전성·점유율, 막·세포 환경, 다른 수용체의 배치는 확인되지 않았다.
이 자료로 당 원자를 포함/제외한 **제한된 구조 조건 비교 입력**은 준비할 수 있지만, F06 실제 계산이나 전체 세포 환경의 접근성을 검증했다고 할 수 없다.
특히 1S78 HER2 말단의 큰 좌표 누락은 해당 부위 접근성·충돌 판단의 정보 공백이다.

## D1 / D2 인계 산출물

| 산출물 | 내용 / 소비 방법 |
|---|---|
| [source-lock.json](assets/a01/source-lock.json) | 공개 URL, 실제 조회 시각, 원본 6개의 byte 수·SHA-256 |
| [sources](assets/a01/sources/) | ASU mmCIF 2개, 공식 assembly mmCIF 3개, P04626 FASTA |
| [review-input.json](assets/a01/generated/review-input.json) | 임시 서비스 v0.1.0 `ReviewInput`에 맞는 실제 공개 서열·업로드 manifest와 사용자가 채택한 명시적 분석 구간 |
| [deposited-sequences.fasta](assets/a01/generated/deposited-sequences.fasta) | 두 entry의 기탁 HER2·Fab 서열 6개. 좌표가 없는 잔기도 서열에는 유지 |
| [chain-mapping.csv](assets/a01/generated/chain-mapping.csv) / [JSON](assets/a01/generated/chain-mapping.json) | 단백질 9사슬 및 비단백질 구성요소의 역할·번호·길이·누락 |
| [residue-mapping.csv](assets/a01/generated/residue-mapping.csv) | 3,264행. 단백질 기탁 위치 3,169개와 비단백질 잔기 95개, 좌표 유무·삽입 코드·원자 수 |
| [structures.json](assets/a01/generated/structures.json) | 서비스 `Structure`에 맞춘 assembly 3개의 D2 기본 대응. 중첩·계산 지표 없음 |
| [artifacts.json](assets/a01/generated/artifacts.json) / [bundle.json](assets/a01/generated/bundle.json) | 실제 구조 파일의 ID·해시·상대 경로, 입력과 번호 체계 설명 |
| [검증 기록](assets/a01/generated/validation.json) | 정상 사례, 번호·서열 오류·누락 주석 삭제 거부, 채택 구간·누락 보존, 오프라인 재생성 검사 10개 |

서비스는 `ReviewInput`의 업로드 이름에 맞는 assembly 1 파일 2개를 multipart로 전달할 수 있다.
`bundle.files.repository_path`는 저장소 루트 기준 로컬 경로이며 공개 API URL이 아니다.
`structures.json`과 `artifacts.json`은 스키마 조각 검증을 통과했지만 실행 ID·지표·의견이 있는 완성 `Result`나 live worker 출력은 아니다.
서비스 파일 등록·3D 선택 검증·B 실행부 연결과 G1 생산자/소비자 검토는 아직 남아 있다.

## 검증과 재현

검증 환경: Windows, Python 3.12.10, Biopython 1.88, jsonschema 4.25.1. CPU로 실행했으며 GPU·NVIDIA 호출은 사용하지 않았다.
실행 방법은 [재현 안내](assets/a01/README.md)에 있다. 공개 원본을 저장했으므로 재생성·검사는 네트워크 없이 가능하다.

검사 결과: 원본 해시 6개, 서열 표와 FASTA 일치, HER2–UniProt 구간 일치, 누락 주석 159개 대응, 전체 원자 보존, assembly 좌표 대조, 서비스 스키마 조각 검증이 통과했다.
별도 검증 10개는 RCSB 집계 수치, 알려진 번호 대응·삽입 코드·당 성분, assembly 분리, 잘못된 서열·번호·주석의 거부, 채택한 구간·파일 대응 및 누락·구간 밖 잔기 보존, 동일 입력 재생성을 확인했다.
프런트엔드에 있던 ASU 파일과 새 원본은 줄바꿈을 정규화하면 동일했다. 다운로드 byte 해시를 보존하기 위해 A-01 원본에만 Git 줄바꿈 변환을 끄고 기존 프런트 파일은 보존했다.

파싱은 [Biopython MMCIF2Dict](https://biopython.org/docs/latest/api/Bio.PDB.MMCIF2Dict.html)로 원본 카테고리를 읽었다.
생성기는 이 두 기준 구조와 단일 model·항등 assembly를 검증하는 조사 도구이며, 임의 사용자 구조를 모두 처리하는 서비스 파서는 아니다.

## 다음 결정과 완료 경계

1. **Q04 공동 검토:** 첫 분석용 두 Fab·각 assembly 1·HER2 23–629·전체 기탁 Fab 구간은 사용자 채택 및 입력 반영 완료다. B의 예측 가능 범위, 서비스의 일반 입력 상한과 최종 데모 선정은 추가 확인한다.
2. **G1 소비자 확인:** 최소 연결 규칙은 사용자 확인 완료다. B·서비스 담당의 별도 확인과 실제 구조의 누락·삽입 코드·당 성분 표시 검증은 남아 있다. 임시 스키마 자체는 변경하지 않았다.
3. **A-02 진입:** 사용자 확인을 받은 범위와 최소 D2 의미로 접촉·충돌·표면 노출·정렬의 정의, 독립 기대값과 첫 공개 구조 계산을 준비한다. 실제 서비스·예측 연동 완료를 진입 근거로 삼지 않는다. 판정 임계값·후보 의견은 아직 만들지 않았다.

기술 조사 산출물은 인계 준비가 됐지만 팀 합의·서비스 통합까지 완료된 상태는 아니다.

## 후보·분석 구간과 팀 연동 검토안

2026-09-26 검토 및 사용자 결정: **아래 후보·assembly·분석 구간을 첫 공개 구조 분석안으로 채택했다.** 생성기와 `a01-2` 입력 묶음에 반영하고 10개 검사로 재검증했다. 팀 소비 확인은 별도 미완료다.
근거는 위 원본 대조 결과, 생성된 `bundle.json`·`review-input.json`·`chain-mapping.json`, [임시 계약](../../frontend-hosting/temporary-contract.md)과 [스키마 원본](../../frontend-hosting/contracts/service.schema.json)이다. RCSB의 [1N8Z](https://www.rcsb.org/structure/1N8Z)·[1S78](https://www.rcsb.org/structure/1S78) 공식 entry도 다시 확인했다.

### 입력 범위 제안

| 항목 | 제안 | 근거와 제한 |
|---|---|---|
| 첫 공개 구조 분석의 후보 | trastuzumab Fab와 pertuzumab Fab 2종 | 확보한 서열·실험 구조를 재사용한다. 새로운 후보나 전체 IgG의 검증을 뜻하지 않는다. |
| 주 구조 | 각각 assembly 1 | 현재 업로드 예시와 동일하다. 1N8Z는 HER2 C·중쇄 B·경쇄 A, 1S78은 HER2 A·중쇄 D·경쇄 C다. 1S78 assembly 2는 같은 후보의 대체 자료로 보존한다. |
| HER2 입력·분석 구간 | 전체 P04626 FASTA를 유지하고 분석 구간만 UniProt 23–629로 지정 | 두 기탁 HER2 서열이 함께 포함하는 구간이다. 공통으로 좌표가 존재하는 구간이라는 뜻은 아니다. 1S78의 630–646은 이 제안의 분석 밖이지만 원본에서 삭제하지 않는다. |
| Fab 분석 구간 | 1N8Z 중쇄 1–220·경쇄 1–214, 1S78 중쇄 1–226·경쇄 1–214 | 각 기탁 FASTA의 전체 구간을 명시한다. 항원 접촉 계산의 원자·제외 규칙은 다음 단계에서 정한다. 1S78 중쇄 223–226의 좌표 누락은 유지한다. |
| 구조 조건 | 원본의 단백질·관측 당 성분·물·이온을 보존 | 단백질 중심 계산과 관측 당 성분을 포함한 조건은 구분한다. 물·이온 포함 여부 및 구체적인 계산 정의는 아직 결정하지 않는다. |
| 입력 크기 | 첫 검증은 확보한 두 assembly 파일과 기탁 서열로 한정 | 서비스의 일반 업로드 크기·서열 길이 상한이나 예측 모델의 허용량은 이 자료만으로 확정할 수 없다. B·서비스 확인이 필요하다. |

HER2를 공통 구간으로 제한하는 대신 23–646으로 잡고 1N8Z의 630–646을 구조 미제공으로 기록하는 대안도 있다. 첫 분석 제안은 양쪽 기탁 서열에 포함된 23–629다. 누락이 많은 1S78에 맞춰 관측 잔기만으로 범위를 축소하면 비교해야 할 자료 공백을 감출 수 있으므로 제안하지 않는다. 이 구간 선택은 두 구조의 공통 입력 범위를 정하는 판단이며 최적의 생물학적 분석 범위로 검증된 결론은 아니다.

### 팀 연동 확인표

| 확인점 | 문서·입력 대조 결과 | 실제 소비자가 확인할 내용 / 상태 |
|---|---|---|
| 후보·파일·assembly | 후보 2개는 스키마의 2–3개 제약과 일치한다. 업로드 예시는 assembly 1이며 별도 대체 구조는 세 번째 후보가 아니다. | B·서비스: 후보 ID와 파일 manifest를 연결하고 대체 assembly를 분리하는지 미확인 |
| 분석 구간 | 표적 구간은 입력 전체 FASTA 기준이며 후보마다 다른 표적 구간을 받는 필드는 없다. 채택 구간을 명시했고 전체 FASTA는 보존했다. | 사용자 채택·실행 입력 반영·기준 입력 검증 완료. B: 임의 입력의 구간·서열 길이·start≤end를 실제로 검사하고 예측용 절단 서열의 번호를 역대응하는지 미확인 |
| 잔기 식별 | HER2 구조 번호 1은 입력 위치 23, 1S78 중쇄 label 84는 author 82+삽입 코드 A다. 비단백질은 서열 위치가 null이다. 계약은 이를 표현할 수 있다. | B·서비스: 표 선택이 같은 model·assembly/operator·label/auth 사슬·번호·삽입 코드의 실제 잔기를 가리키는지 미확인 |
| 누락 처리 | `has_coordinates=false`와 null 서열 위치는 서로 다른 의미다. 1S78 HER2 label 565–624, 중쇄 223–226의 좌표는 없다. | B·서비스: 누락을 가짜 좌표나 측정값 0으로 바꾸지 않고 이유와 영향 범위를 표시하는지 미확인 |
| 정렬·단위 | 현재 Å, `alignment=null`; assembly 생성은 구조 간 중첩이 아니다. 계약은 대상→기준 변환과 적용 여부를 별도 표현한다. | A·B·서비스: 첫 정렬에서 기준 잔기·행렬·적용 여부를 맞추고 viewer가 중복 적용하지 않는지 미확인 |
| 파일·결과 인계 | 저장소 상대 경로는 공개 URL이 아니며 기존 구조·artifact 조각은 완성 Result가 아니다. | B·서비스: work_dir 안의 실제 파일·해시를 등록하고 artifact URL로 로딩하는지 미확인. 계산 미실행 값은 not_run으로 전달 |

대조한 범위에서는 입력 의미와 계약 사이의 확정된 모순을 발견하지 않았다. 범위 순서·서열 길이 검증과 실제 파일·화면 연결은 JSON Schema만으로 보장되지 않는 추가 검증 사항이다. 사용자 또는 소비자 요구가 후보별로 서로 다른 표적 구간을 필수로 요구하면 현재 단일 `target.analysis_range`와의 충돌 여부를 다시 검토한다.

**결정 상태:** 사용자가 첫 분석 범위와 아래 최소 연결 규칙에 동의하고 다음 계산 단계로 진행하도록 요청했다. 입력 생성·재검증과 사용자 기준의 범위·연결 검토를 완료했다. B의 예측 가능 범위, 서비스의 실제 파일·잔기 소비 검증 및 담당자별 별도 동의는 미완료이며 사용자 결정을 팀원 전체의 동의로 간주하지 않는다. 이 미완료 항목은 서비스·예측 통합에서 확인하고, 사용자 승인 범위의 로컬 공개 구조 계산은 진행할 수 있다. 범위·계약 모순이 확정되면 Astra High 전환 조건으로 보고하고 영향·대안을 검토한다. 최종 데모 선정·실제 예측·서비스 통합 완료는 별도로 검증한다.

### 사용자 확인을 받은 최소 연결 규칙

2026-09-26 사용자가 표와 3D의 같은 잔기 대응, 좌표 누락을 0·문제없음으로 표시하지 않는 규칙, 동일 분석 파일 사용과 중복 정렬 방지에 동의했다. 직전 설명의 누락 처리 방식도 이 기준으로 적용한다.

1. 표와 3D는 같은 구조의 같은 아미노산을 가리킨다. 전체 서열 위치를 구조 번호로 직접 대입하지 않고 사슬·label/auth 번호·삽입 코드·model·assembly/operator 대응을 보존한다.
2. 서열에는 있지만 좌표가 없는 부분은 ‘위치 정보 없음’으로 표시한다. 임의 좌표로 채우지 않고 위치가 필요한 계산에서 제외하며 제외 위치·범위·이유를 남긴다. 나머지 부분의 계산값은 관측 범위에만 한정하고, 누락 때문에 판단할 수 없는 항목은 자료 부족으로 보류한다. 누락은 측정된 0이나 충돌 없음이 아니다.
3. 화면은 분석에 사용한 동일 파일을 사용한다. 정렬 기준과 변환 적용 여부를 전달해 이미 정렬한 좌표를 중복 변환하지 않는다.

이 확인은 연결 규칙의 사용자 승인이다. 실제 화면 구현·파일 등록·다운로드·예측 실행 성공이나 다른 담당자의 응답을 증명하지 않는다.

### 현재 소비 코드 대조 및 확인 요청 항목

현재 checkout의 [화면 설명](../../../frontend/README.md), [구조 로더](../../../frontend/src/StructurePreview.tsx), [잔기 선택 코드](../../../frontend/src/molecular-viewer.ts)를 읽었다. 화면은 `/structures/{pdb}.cif`와 별도 `contacts.json`을 읽고 assembly 1을 생성하며 label 사슬·label 잔기 번호로 선택한다. 이는 공개 구조 미리보기로 명시된 구현이다. 이번 `ReviewInput`·`Structure`·artifact 파일 묶음의 실제 소비 구현이나 팀 확인으로 간주하지 않는다. author 번호를 label 번호 자리에 넣으면 선택 대상이 달라지므로 adapter에서 반드시 대응해야 한다. 이 미연결 상태는 기존 임시 계약과의 확정된 설계 모순은 아니다.

- B 담당 확인 요청: HER2 위치는 전체 P04626, 항체 위치는 기탁 Fab 기준으로 유지하고, 누락 좌표는 계산 가능한 0으로 바꾸지 않으며, 두 assembly 1을 두 후보에 연결하는 최소 입력 의미에 동의하는가? 예측용 절단·허용량 검증은 별도 상태로 기록할 수 있는가?
- 서비스 담당 확인 요청: label/auth·삽입 코드·좌표 유무를 보존한 구조 대응을 소비하고, 실제 파일·해시를 등록한 artifact 참조로 로드하며, 정렬 적용 여부를 존중하는 최소 결과 의미에 동의하는가? 미리보기의 정적 경로·잔기 목록과 실제 결과 연결은 별도 구현임을 확인하는가?
- 확인 근거: 사용자가 위 최소 연결 규칙에 동의하고 다음 단계 진행을 요청했다. 다른 담당자의 별도 응답·메시지 발송 기록은 없다. 실제 잔기 강조·누락 표시·파일 다운로드 성공은 아직 검증하지 않았다.
