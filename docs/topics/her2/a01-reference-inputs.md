# A-01 공개 구조 기준 입력 조사

확인일: 2026-09-26 KST. 작업 브랜치: `feat/structure-analysis`.
상태: **자료 확보·대응표 생성·기술 검증 완료, Q04와 G1 공동 검토 대기**.
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
D1 예시는 재현 가능한 첫 입력을 위해 assembly 1을 사용한다. 이는 품질 우열이나 최종 분석 assembly를 확정한 결정이 아니다.
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
| [review-input.json](assets/a01/generated/review-input.json) | 임시 서비스 v0.1.0 `ReviewInput`에 맞는 실제 공개 서열·업로드 manifest. 모든 analysis_range는 미승인 null |
| [deposited-sequences.fasta](assets/a01/generated/deposited-sequences.fasta) | 두 entry의 기탁 HER2·Fab 서열 6개. 좌표가 없는 잔기도 서열에는 유지 |
| [chain-mapping.csv](assets/a01/generated/chain-mapping.csv) / [JSON](assets/a01/generated/chain-mapping.json) | 단백질 9사슬 및 비단백질 구성요소의 역할·번호·길이·누락 |
| [residue-mapping.csv](assets/a01/generated/residue-mapping.csv) | 3,264행. 단백질 기탁 위치 3,169개와 비단백질 잔기 95개, 좌표 유무·삽입 코드·원자 수 |
| [structures.json](assets/a01/generated/structures.json) | 서비스 `Structure`에 맞춘 assembly 3개의 D2 기본 대응. 중첩·계산 지표 없음 |
| [artifacts.json](assets/a01/generated/artifacts.json) / [bundle.json](assets/a01/generated/bundle.json) | 실제 구조 파일의 ID·해시·상대 경로, 입력과 번호 체계 설명 |
| [검증 기록](assets/a01/generated/validation.json) | 정상 사례, 번호·서열 오류·누락 주석 삭제 거부, 오프라인 재생성 검사 9개 |

서비스는 `ReviewInput`의 업로드 이름에 맞는 assembly 1 파일 2개를 multipart로 전달할 수 있다.
`bundle.files.repository_path`는 저장소 루트 기준 로컬 경로이며 공개 API URL이 아니다.
`structures.json`과 `artifacts.json`은 스키마 조각 검증을 통과했지만 실행 ID·지표·의견이 있는 완성 `Result`나 live worker 출력은 아니다.
서비스 파일 등록·3D 선택 검증·B 실행부 연결과 G1 생산자/소비자 검토는 아직 남아 있다.

## 검증과 재현

검증 환경: Windows, Python 3.12.10, Biopython 1.88, jsonschema 4.25.1. CPU로 실행했으며 GPU·NVIDIA 호출은 사용하지 않았다.
실행 방법은 [재현 안내](assets/a01/README.md)에 있다. 공개 원본을 저장했으므로 재생성·검사는 네트워크 없이 가능하다.

검사 결과: 원본 해시 6개, 서열 표와 FASTA 일치, HER2–UniProt 구간 일치, 누락 주석 159개 대응, 전체 원자 보존, assembly 좌표 대조, 서비스 스키마 조각 검증이 통과했다.
별도 검증 9개는 RCSB 집계 수치, 알려진 번호 대응·삽입 코드·당 성분, assembly 분리, 잘못된 서열·번호·주석의 거부, 동일 입력 재생성을 확인했다.
프런트엔드에 있던 ASU 파일과 새 원본은 줄바꿈을 정규화하면 동일했다. 다운로드 byte 해시를 보존하기 위해 A-01 원본에만 Git 줄바꿈 변환을 끄고 기존 프런트 파일은 보존했다.

파싱은 [Biopython MMCIF2Dict](https://biopython.org/docs/latest/api/Bio.PDB.MMCIF2Dict.html)로 원본 카테고리를 읽었다.
생성기는 이 두 기준 구조와 단일 model·항등 assembly를 검증하는 조사 도구이며, 임의 사용자 구조를 모두 처리하는 서비스 파서는 아니다.

## 다음 결정과 완료 경계

1. **Q04 공동 검토:** 두 Fab를 기준 데모 입력으로 채택할지, 두 개로 충분한지, 전체 기탁 Fab와 HER2의 어느 구간을 분석할지 결정한다. 길이가 다른 HER2 서열과 1S78 말단 누락을 검토 근거로 사용한다.
2. **G1 소비자 확인:** B·서비스가 동일 입력·사슬·잔기·assembly를 해석하고, 실제 구조에서 누락·삽입 코드·당 성분을 표시할 수 있는지 확인한다. 임시 스키마 자체는 변경하지 않았다.
3. **A-02 진입:** 위 범위와 최소 D2 계약을 검토한 뒤 접촉·충돌·표면 노출·정렬의 정의, 독립 기대값과 첫 계산을 준비한다. 이번 조사에서는 판정 임계값·후보 의견을 만들지 않았다.

기술 조사 산출물은 인계 준비가 됐지만 팀 합의·서비스 통합까지 완료된 상태는 아니다.
