# A-01 기준 입력 묶음 재현

조사 결과·한계·Q04/G1 검토 항목은 [A-01 보고서](../../a01-reference-inputs.md)를 따른다.
저장소 루트에서 Python 3.11 이상과 [requirements.txt](requirements.txt)의 패키지로 실행한다.

```powershell
python -m pip install -r docs/topics/her2/assets/a01/requirements.txt
python docs/topics/her2/assets/a01/build_inputs.py
python docs/topics/her2/assets/a01/test_inputs.py
```

프로젝트 가상환경을 사용할 때는 `python` 대신 `.venv/Scripts/python.exe`를 사용한다.
`build_inputs.py`는 잠긴 원본을 검증한 뒤 `generated/`의 파생 산출물을 재생성하며 원본은 수정하지 않는다.
`test_inputs.py`는 10개 검사를 실행하고 `generated/validation.json`에 결과를 저장한다. 대량 잔기·원자 목록은 터미널에 출력하지 않는다.

원본은 `sources/`에 포함돼 있어 평소 실행에 네트워크가 필요 없다.
공개 배포 원본과 재대조하거나 누락된 같은 버전 파일을 복구할 때만 다음을 실행한다.

```powershell
python docs/topics/her2/assets/a01/fetch_sources.py
```

다운로드 대상은 `files.rcsb.org`와 `rest.uniprot.org`의 공개 파일 6개로 고정돼 있다.
파일이 잠긴 해시나 기존 로컬 파일과 다르면 덮어쓰지 않고 실패한다. 원격 개정이 발생하면 차이를 검토해 새 조사본으로 관리해야 한다.
`source-lock.json`의 조회 시각은 최초 snapshot 시각이며, 재대조가 성공해도 자동 변경하지 않는다.

`sources/*`는 원본 byte 해시를 보존하도록 Git 줄바꿈 변환을 끈다.
공식 mmCIF 원본의 줄 끝 공백도 보존하므로 `sources/*.cif`에만 해당 공백 검사 예외를 적용한다. 원본 무결성은 SHA-256으로 검증한다.
`generated/`의 CSV는 UTF-8이며 빈 셀은 해당 값 없음/null, 좌표 유무는 `True`/`False`로 기록한다.
잔기 identity에는 label/auth 사슬, 번호와 삽입 코드가 필요하며, 비단백질에는 label_seq_id가 없다.
`has_coordinates`는 원자 레코드 존재 여부다. positive occupancy 원자 수도 별도 기록했고 이번 두 파일에는 zero occupancy 원자가 없다.

2026-09-26 사용자가 첫 공개 구조 분석 범위를 채택했다. `a01-2` 입력은 HER2 UniProt 23–629, 1N8Z 중쇄 1–220·경쇄 1–214, 1S78 중쇄 1–226·경쇄 1–214를 명시한다. 전체 입력 서열·좌표 누락·구간 밖 대응표는 보존한다.
각 assembly 1을 첫 분석에 사용하며 1S78 assembly 2는 같은 pertuzumab 후보의 대체 자료다. `analysis_ranges_approved=true`는 이 사용자 결정만 뜻하며, 최종 데모 선정·팀 소비 확인·첫 계산 완료를 뜻하지 않는다.
전체 설명은 [bundle.json](generated/bundle.json), 기탁 잔기의 원자 존재·번호·UniProt 대응은 [residue-mapping.csv](generated/residue-mapping.csv), 원본 링크·해시는 [source-lock.json](source-lock.json)에 있다.
