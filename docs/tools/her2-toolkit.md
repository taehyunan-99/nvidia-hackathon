# HER2 항체 후보 검토에 필요한 도구

`nvidia/docs/18-bionemo-molecule-protein-skills-tools.md`(2026-09-22 조사)와 `24-her2-antibody-agent-design.md`(2026-09-24 설계)에서 관련 항목을 선별했다.
편집일: 2026-09-24. 설치·API 실행·성능 검증 결과가 아닌 후보 설계 참고자료다.

## 설계와 실행의 연결

[Nemotron·NAT의 판단 흐름과 전체 단계](../topics/her2/agent-design.md)를 기준으로 데이터를 조회하고, 공개 구조로 충분한지 판단한 뒤 필요한 예측만 수행한다.
스킬은 실행 절차의 참고자료이며 실제 호출 함수·파일 검증·오류 처리는 구현해야 한다.

## 구조 예측용 NVIDIA 스킬

| 도구 / 스킬명 | 어떤 도구인가? | 입력 → 출력 | 가능한 활용 |
|---|---|---|---|
| [MSA-Search / `msa-search-nim`](https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit/tree/main/nim-skills/msa-search-nim) | 유사 서열을 찾아 다중서열정렬 생성 | 단백질 서열 → A3M/FASTA 정렬 | 구조 예측용 진화 정보 준비, 복합체용 paired MSA |
| [Boltz-2 / `boltz2-nim`](https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit/tree/main/nim-skills/boltz2-nim) | 복합체 구조 및 선택적 리간드 친화도 예측 | 서열·리간드 SMILES/CCD 등 → mmCIF·신뢰도·친화도 추정 | 후보 리간드 비교, 복합체 예측, 설계 후보 재평가 |

MSA는 유사 서열의 정렬이며 PDB·mmCIF는 3D 구조 파일 형식이다.
Boltz-2의 소분자 친화도 기능을 항체–단백질 결합력 평가에 그대로 적용하지 않는다.
인터페이스 신뢰도·구조 일관성은 후속 검토를 돕는 신호이며 실험적 결합·효능을 증명하지 않는다.
[결과 해석의 원출처](https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit/blob/main/nim-skills/boltz2-nim/references/science.md).

## 데이터 확보와 시각화

| 도구·데이터 | 역할 | 에이전트에서 가능한 기능 |
|---|---|---|
| [RCSB PDB API](https://www.rcsb.org/docs/programmatic-access/web-apis-overview) | 단백질·복합체 구조 데이터 | 구조 검색, PDB 정보 조회, 표적 구조 확보 |
| [UniProt API](https://www.uniprot.org/help/api) | 단백질 서열·주석 데이터 | 이름·accession으로 서열과 기능 정보 확인 |
| [Mol*](https://molstar.org/) | 웹 기반 분자 3D 시각화 | 단백질·리간드·예측 구조를 웹 화면에서 비교 |

## HER2 설계에 기록된 검증 도구

- Thera-SAbDab: 항체 서열·자료 확보 후보. 실제 접근 경로·사용 조건은 구현 전에 확인한다.
- [Biopython](https://biopython.org/docs/latest/api/Bio.PDB.html) + NumPy: 사슬·잔기 번호 대응, 접촉·충돌 검사, 구조 정렬과 비교.
- [FreeSASA](https://freesasa.github.io/): 표면 노출도 계산. 당쇄·누락 구조 등 입력의 범위를 결과에 남긴다.
- 선택적 IEDB Query API: 추가 근거 조회 후보이며 필수 경로로 확정하지 않는다.

## 먼저 검증할 경로

공개 구조 [1N8Z](https://www.rcsb.org/structure/1N8Z)·[1S78](https://www.rcsb.org/structure/1S78)로 번호 대응과 접촉 부위 재현을 검증하고, 실제 계정으로 Boltz-2 한 건을 호출한다.
정상 입력 외 서열 불일치·구조 누락·API 실패에서 보류와 오류 설명이 되는지 확인한다.
로컬 GPU 없는 호스팅 경로도 API 접근·quota·응답 시간·라이선스 검증이 필요하다.

출처 스냅샷: [BioNeMo Agent Toolkit](https://github.com/NVIDIA-BioNeMo/bionemo-agent-toolkit/tree/0e67a612e4045f007e38fa77adc8f3ebfc5616b6).
표의 main 링크는 달라질 수 있으므로 구현 시 버전을 고정한다.
소분자 생성·유전체·추가 학습·신규 바인더 생성 경로는 현재 설계 범위에서 제외했다.
