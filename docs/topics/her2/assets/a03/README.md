# A-03 관측 당 비교 재현과 연결

[계산 정의·해석 경계](../../a03-glycan-context.md)를 따른다. A-01/A-02 원본·계산 결과를 읽기만 하는 오프라인 실행이며 API 키·GPU·외부 모델 호출이 필요 없다. A-02의 [requirements.txt](../a02/requirements.txt)를 사용한다.

## 실행

저장소 루트의 기존 `.venv`에서 실행한다.

```powershell
.venv/Scripts/python.exe docs/topics/her2/assets/a03/compare.py
.venv/Scripts/python.exe docs/topics/her2/assets/a03/test_compare.py
```

`compare.py --out <directory>`로 결과를 별도 위치에 재생성할 수 있다. 검사는 임시 폴더에서 전체 계산을 한 번 더 실행하므로 시간이 걸린다. 외부 예측 입력을 받는 일반 서비스 함수가 아니라 승인된 두 공개 구조의 재현 진입점이다.

## 산출물

| 파일 | 내용 |
|---|---|
| `generated/summary.json` | 동일 단백질 fingerprint, 조건별 총/역할별 표면적·차이, 두 해상도, 원자·잔기 누락 |
| `generated/glycan-inventory.json` | 당의 원본 identity·관측 원자 이름·성분 정의·공유결합 양 끝 대응과 거리 |
| `generated/*-protein-sasa.csv` | 관측 단백질 잔기별 core/context/감소량과 전체 잔기 대응, 960/1920점 각각 |
| `generated/service-fragments.json` | 기존 계약에 맞는 core/context Condition과 Evidence 추가분, 해시로 고정한 A-02 의존 파일 |
| `generated/provenance.json` | 원본·구현·의존 파일·결과 해시와 실제 계산 시간 |
| `generated/validation.json` | 실제 검사 결과와 검사 코드 해시 |

## 로직 B 소비 규칙

1. `service-fragments.json.a02_dependency.repository_path`에서 A-02 자료를 읽고 `sha256`을 확인한다. 그 파일의 `structures`, `artifacts`, `files`와 정렬 정보를 재사용한다. A-03은 대량 잔기 대응표와 구조를 복제하지 않는다. A-02 의존 파일을 바꿨다면 A-03을 다시 검증한다.
2. A-03의 `conditions`, `evidence`를 함께 소비한다. A-02와 충돌하지 않는 `a03-*` ID를 사용한다. `observed_glycan_protein_sasa_reduction`은 **같은 후보의 A-03 core와 context 간 차이**이고, `surface_exposure`는 양 조건에서 단백질 표면만 뜻한다. 기본 Evidence는 960점이며 1920점·역할별 결과는 summary에 있다.
3. 두 조건이 같은 원본 구조 ID를 참조해도 포함 성분은 다르다. 원본 assembly에는 당·일부 물·이온이 함께 있으므로 core/context를 표시할 때 Condition과 당 목록의 원본 identity를 사용해 성분을 선택해야 한다. 전체 파일 원자를 그대로 계산 조건으로 간주하지 않는다.
4. 실제 실행의 후보 ID로 바꿀 때 조건·근거·구조 참조를 함께 바꾼다. A-02 파일 경로는 저장소 상대 경로이며 API URL이나 작업 폴더가 아니다. 다운로드 파일 등록·실행 ID·보고서 의견 조립은 B/서비스의 후속 연결이다.

`baseline.validate_fragments`와 A-03 의존 해시 검사로 계약 호환성을 확인한다. 이는 실제 B 실행·NAT·worker·화면·다운로드 통합 검증을 대신하지 않는다. 결합력 순위나 정식 충돌 판정을 추가하지 않는다.
