# A-02 공개 구조 계산 재현

정의·제외 규칙·출처·해석 경계는 [계산 기준](../../a02-structure-metrics.md)을 따른다.
승인된 A-01 두 구조 전용 오프라인 분석이다. 원본 mmCIF·전체 FASTA·A-01 산출물을 수정하지 않는다.

## 실행

저장소 루트에서 Python 3.11 이상과 [requirements.txt](requirements.txt)의 환경을 사용한다.
현재 프로젝트의 `.venv`에 설치된 Biopython·NumPy·jsonschema로 실행할 수 있다.

```powershell
.venv/Scripts/python.exe docs/topics/her2/assets/a02/analyze.py
.venv/Scripts/python.exe docs/topics/her2/assets/a02/test_metrics.py
```

`analyze.py --out <directory>`는 별도 위치에 같은 결과를 생성한다.
계산은 CPU에서 실행하며 네트워크·GPU·NVIDIA 키를 사용하지 않는다.
테스트는 전체 재생성을 포함하므로 표면적 계산 시간만큼 추가로 걸린다.
이번 Windows/Python 3.12.10 실행에서 두 구조·두 표면 해상도를 모두 계산하는 데 258.88초가 걸렸다.
이는 이 기기의 단일 실행 관측이며 서비스 응답 시간 보장이 아니다. 최대 메모리·컨테이너 성능은 미측정이다.
실제 서비스에서 매번 계산할지, 입력·파라미터·구현 해시가 일치하는 결과를 재사용할지는 통합 단계에서 정한다.

## 파일

| 파일 | 용도 |
|---|---|
| `metrics.py` | 중원자 거리·접촉·기하학적 겹침, Shrake–Rupley SASA, SVD 정렬 함수 |
| `analyze.py` | A-01 입력·원본 검증, 승인 구간/누락 적용, 계산 및 서비스 계약 조각 생성 |
| `test_metrics.py` | 해석식·합성 좌표·잘못된 대응·누락·공개 구조·계약·재생성 검증 |
| `generated/summary.json` | 계산 조건·후보별 관측 범위·누락·지표·표면 해상도 차이·정렬 요약 |
| `generated/*-contact-pairs.csv` | 접촉 원자 쌍의 거리·원소 반지름 겹침·양쪽 잔기의 전체 identity |
| `generated/*-residue-sasa.csv` | 관측 잔기별 복합체/분리 SASA 및 양쪽 각각의 매몰 표면적 |
| `generated/service-fragments.json` | 실제 `Structure`, `Condition`, `Evidence`, `Artifact`와 원본 파일 참조 |
| `generated/provenance.json` | 입력·구현·출력 해시, 사용한 원본, 측정 실행 시간 |
| `generated/validation.json` | 실행한 검사 이름·결과·실패 상세 |

대량 대응표와 원자 쌍은 스크립트로 처리하고 대화에는 summary의 요약만 출력한다.
JSON 생성과 Git의 결과 CSV 줄바꿈을 LF로 고정해 Windows에서도 저장된 파일의 byte 해시를 유지한다.

## B·서비스에서 연결할 때

`service-fragments.json`은 완성된 `Result`나 `LogicOutput`이 아니다. 실행 ID·의견·다운로드용 결과 파일은 B가 실제 실행 맥락에서 조립한다.
`files[].repository_path`는 저장소 상대 경로이며 API URL이나 서비스가 지정한 work_dir가 아니다. 운영 adapter는 같은 bytes를 work_dir에 등록하고 해시를 다시 확인해야 한다.

- 후보는 A-01의 `reference-trastuzumab-fab`, `reference-pertuzumab-fab`이다. 실행의 후보 ID로 변환할 때 관련 조건·근거·구조 참조를 함께 바꾼다.
- 실험 구조가 같더라도 A-01의 assembly 파일과 기존 화면의 ASU 파일은 byte 해시가 다르다. 근거와 파일을 섞지 않는다.
- `residue_mapping`은 원본의 전체 범위를 보존한다. 계산된 접촉 잔기에는 정확한 label/auth·삽입 코드·전체 서열 위치가 있고, 좌표 누락도 구조 대응표에서 조회할 수 있다.
- 1S78의 alignment는 1N8Z 기준이며 `applied=false`다. 원본에 변환을 적용하지 않았다. 화면은 단위 Å·행 우선 저장·열벡터 곱 의미를 확인해야 한다.
- `surface_exposure`의 값은 관측 단백질 복합체 전체 SASA다. 특정 잔기 접근성 비율이나 전체 세포 환경의 항체 접근성으로 해석하지 않는다.
- `atom_clash`는 `not_run`, 전체 구간 접근성은 `unknown`이다. 별도 기하학적 겹침 값을 이 상태 대신 사용하지 않는다.

현재 서비스·worker·화면·B 실행부 코드는 변경하지 않았다. 실제 런타임 연결과 예측 구조·당 포함 조건의 검증은 후속 작업이다.
