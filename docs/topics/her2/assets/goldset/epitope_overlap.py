"""표적쪽 접촉 잔기를 공통 좌표로 옮겨 에피토프를 서로 겹쳐 본다.

엔트리마다 표적 construct의 시작 위치가 달라 label_seq_id를 그대로 비교하면
안 된다. 1N8Z의 표적 서열을 기준으로 삼고 difflib로 위치를 옮긴다.
"""
import difflib
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
GOLD = str(GENERATED)
CIF = str(HERE / "cif")
sys.path.insert(0, str(ROOT))

from logic import structures  # noqa: E402

ROLE_TARGET = {"3BE1": "1", "3WSQ": "1", "5O4G": "1", "6ATT": "1", "6BGT": "1",
               "9L1S": "1", "9T3R": "3", "9T3S": "3", "4P59": "1", "8YRY": "1"}


def target_seq(pid):
    if pid in ("1N8Z", "1S78"):
        path = f"{ROOT}/frontend/public/structures/{pid}.cif"
        ents, _ = structures.parse_entities(open(path, encoding="utf-8").read())
        for e in ents:
            if "erbb-2" in (e.description or "").lower() or "her2" in (e.description or "").lower():
                return e.sequence
        return ""
    data = json.load(open(f"{GOLD}/pdb-sequences.json"))
    want = ROLE_TARGET[pid]
    for e in data[pid]["entities"]:
        if e["entity_id"] == want:
            return e["sequence"]
    return ""


def remap(seq_from, seq_to, positions):
    """seq_from의 1-based 위치를 seq_to의 1-based 위치로 옮긴다. 대응 없으면 버린다."""
    sm = difflib.SequenceMatcher(None, seq_from, seq_to, autojunk=False)
    m = {}
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            m[a + k + 1] = b + k + 1
    return sorted({m[p] for p in positions if p in m}), sum(1 for p in positions if p not in m)


ref = target_seq("1N8Z")
data = json.load(open(f"{GOLD}/reference-contacts.json"))
by_pdb = {r["pdb"]: r for r in data}

canon = {}
for r in data:
    pid = r["pdb"]
    if r["target_kind"] != "HER2":
        continue
    seq = target_seq(pid)
    if not seq:
        print(pid, "표적 서열 없음")
        continue
    c = r["copies"][0]
    mapped, dropped = remap(seq, ref, c["target_side_resnum"])
    canon[pid] = set(mapped)
    print(f"{pid:6} 접촉 {c['target_side_count']:>3} → 1N8Z 좌표 {len(mapped):>3}개 (대응 실패 {dropped})")

print()
print("1N8Z 에피토프와의 겹침 (Jaccard, 교집합/합집합)")
base = canon.get("1N8Z", set())
for pid, s in canon.items():
    if pid == "1N8Z":
        continue
    inter = len(base & s)
    union = len(base | s)
    print(f"  {pid:6} 교집합 {inter:>3} / 합집합 {union:>3} = {inter/union:.3f}"
          if union else f"  {pid:6} 비교 불가")

print()
print("1S78 에피토프와의 겹침")
base2 = canon.get("1S78", set())
for pid, s in canon.items():
    if pid in ("1S78",):
        continue
    inter = len(base2 & s)
    union = len(base2 | s)
    print(f"  {pid:6} 교집합 {inter:>3} / 합집합 {union:>3} = {inter/union:.3f}"
          if union else f"  {pid:6} 비교 불가")

json.dump({k: sorted(v) for k, v in canon.items()},
          open(f"{GOLD}/epitopes-1n8z-coords.json", "w"), ensure_ascii=False, indent=1)
print(f"\n저장: {GOLD}/epitopes-1n8z-coords.json")
