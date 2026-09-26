"""실제 PDB 10건을 후보로 넣었을 때 구조 조회가 뭐라고 하는지 본다.

모델도 네트워크도 부르지 않는다. logic.structures.find_structure만 쓴다.
카탈로그에는 1N8Z·1S78만 있으므로 10건의 정답은 전부 예측 경로다.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GENERATED = HERE / "generated"


def _repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").exists() and (p / "logic").is_dir():
            return p
    raise SystemExit("저장소 뿌리를 찾지 못했다(pyproject.toml + logic/).")


ROOT = _repo_root(HERE)
sys.path.insert(0, str(ROOT))

from logic import structures  # noqa: E402

# (중쇄, 경쇄, 표적) entity_id. RCSB 설명 문자열을 읽고 손으로 확인했다.
ROLE = {
    "3BE1": (2, 3, 1), "3WSQ": (3, 2, 1), "5O4G": (3, 2, 1), "6ATT": (2, 3, 1),
    "6BGT": (3, 2, 1), "9L1S": (3, 2, 1), "9T3R": (2, 1, 3), "9T3S": (1, 2, 3),
    "4P59": (2, 3, 1), "8YRY": (2, 3, 1),
}
TARGET_KIND = {"4P59": "HER3", "8YRY": "HER3"}

data = json.loads((GENERATED / "pdb-sequences.json").read_text(encoding="utf-8"))
print(f"{'PDB':6} {'표적':5} {'중쇄':5} {'경쇄':5} {'조회 결과':28} {'정답':12}")
rows = []
for pid, v in data.items():
    h_id, l_id, t_id = ROLE[pid]
    ents = {int(e["entity_id"]): e for e in v["entities"]}
    heavy, light, target = ents[h_id], ents[l_id], ents[t_id]
    m = structures.find_structure(f">h\n{heavy['sequence']}", f">l\n{light['sequence']}")
    if m.pdb_id is None:
        got = "일치 없음"
    elif m.complete:
        got = f"{m.pdb_id} 완전 일치"
    else:
        got = f"{m.pdb_id} 부분({'중쇄만' if m.heavy_exact else '경쇄만'})"
    # 완전 일치가 아니면 예측 경로가 정답이다.
    ok = "완전 일치" not in got
    rows.append({"pdb": pid, "target": TARGET_KIND.get(pid, "HER2"), "match": got,
                 "gold": "predict", "pass": ok,
                 "lens": [target["length"], heavy["length"], light["length"]]})
    print(f"{pid:6} {TARGET_KIND.get(pid,'HER2'):5} {heavy['length']:<5} {light['length']:<5} "
          f"{got:28} {'predict':12} {'OK' if ok else 'FAIL'}")

(GENERATED / "lookup-result.json").write_text(
    json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
print()
print("부분 일치 건수:", sum(1 for r in rows if "부분" in r["match"]))
print("완전 일치 건수:", sum(1 for r in rows if "완전" in r["match"]))
print("정답:", sum(1 for r in rows if r["pass"]), "/", len(rows))
