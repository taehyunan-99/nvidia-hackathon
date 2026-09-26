"""결정 구조에서 표적–항체 접촉 잔기를 계산해 대조용 기준으로 저장한다.

저장소의 logic.contacts(4.5A 컷오프, 중원자)를 그대로 쓴다. 새 알고리즘을
만들지 않는다. 1N8Z는 저장소가 이미 39잔기라고 적어 둔 값이 있어 검산에 쓴다.
"""
import json
import re
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

from logic import contacts  # noqa: E402

CATALOG = f"{ROOT}/frontend/public/structures"

# 새로 받은 10건의 entity 역할. RCSB 설명 문자열을 직접 읽고 손으로 확인했다.
ROLE = {
    "3BE1": {"2": "heavy", "3": "light", "1": "target"},
    "3WSQ": {"3": "heavy", "2": "light", "1": "target"},
    "5O4G": {"3": "heavy", "2": "light", "1": "target"},
    "6ATT": {"2": "heavy", "3": "light", "1": "target"},
    "6BGT": {"3": "heavy", "2": "light", "1": "target"},
    "9L1S": {"3": "heavy", "2": "light", "1": "target"},
    "9T3R": {"2": "heavy", "1": "light", "3": "target"},
    "9T3S": {"1": "heavy", "2": "light", "3": "target"},
    "4P59": {"2": "heavy", "3": "light", "1": "target"},
    "8YRY": {"2": "heavy", "3": "light", "1": "target"},
}
TARGET_KIND = {"4P59": "HER3", "8YRY": "HER3"}

_HEAVY = re.compile(r"heavy chain", re.I)
_LIGHT = re.compile(r"light chain", re.I)
_TARGET = re.compile(r"erbB-2|HER2", re.I)


def struct_asym(text):
    """label_asym_id -> entity_id. _struct_asym 루프를 읽는다."""
    out = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "_struct_asym.id":
            cols, j = [], i
            while j < len(lines) and lines[j].strip().startswith("_struct_asym."):
                cols.append(lines[j].strip())
                j += 1
            ai, ei = cols.index("_struct_asym.id"), cols.index("_struct_asym.entity_id")
            while j < len(lines) and not lines[j].startswith("#"):
                p = lines[j].split()
                if len(p) >= len(cols):
                    out[p[ai]] = p[ei]
                j += 1
            break
    return out


def roles_for(pid, text):
    if pid in ROLE:
        return ROLE[pid]
    # 카탈로그의 두 건은 저장소와 같은 방식(설명 문자열)으로 역할을 잡는다.
    from logic import structures
    ents, _ = structures.parse_entities(text)
    r = {}
    for e in ents:
        d = e.description or ""
        if _HEAVY.search(d):
            r[e.entity_id] = "heavy"
        elif _LIGHT.search(d):
            r[e.entity_id] = "light"
        elif _TARGET.search(d):
            r[e.entity_id] = "target"
    return r


def run(pid, path):
    text = open(path, encoding="utf-8").read()
    asym2ent = struct_asym(text)
    roles = roles_for(pid, text)
    tgt = {a for a, e in asym2ent.items() if roles.get(e) == "target"}
    ab = {a for a, e in asym2ent.items() if roles.get(e) in ("heavy", "light")}
    if not tgt or not ab:
        return {"pdb": pid, "error": f"역할 미해결 target={sorted(tgt)} ab={sorted(ab)}"}
    atoms = contacts.parse_atoms(text)
    # 비대칭 단위에 복합체가 여러 벌 들어 있는 구조가 있다(1S78은 2벌).
    # 예측 구조는 한 벌이므로 표적 사슬마다 따로 모아야 대조가 맞는다.
    copies = []
    for t in sorted(tgt):
        pairs = contacts.contact_residues(atoms, {t}, ab)
        if not pairs:
            continue
        t_side = sorted(n for c, n in pairs if c == t)
        a_side = sorted((c, n) for c, n in pairs if c in ab)
        touched = sorted({c for c, _ in a_side})
        copies.append({
            "target_chain": t,
            "antibody_chains": touched,
            "total_residues": len(pairs),
            "target_side_count": len(t_side),
            "antibody_side_count": len(a_side),
            "target_side_resnum": t_side,
            "antibody_side": [f"{c}:{n}" for c, n in a_side],
        })
    return {
        "pdb": pid,
        "target_kind": TARGET_KIND.get(pid, "HER2"),
        "cutoff_angstrom": contacts.CUTOFF_ANGSTROM,
        "target_chains": sorted(tgt),
        "antibody_chains": sorted(ab),
        "copy_count": len(copies),
        "copies": copies,
    }


out = []
for pid in ["1N8Z", "1S78"]:
    out.append(run(pid, f"{CATALOG}/{pid}.cif"))
for pid in ROLE:
    out.append(run(pid, f"{CIF}/{pid}.cif"))

print(f"{'PDB':6} {'표적':5} {'벌':3} {'벌당 총':8} {'표적쪽':7} {'항체쪽':7}")
for r in out:
    if "error" in r:
        print(f"{r['pdb']:6} ERROR {r['error']}")
        continue
    tot = ",".join(str(c["total_residues"]) for c in r["copies"])
    ts = ",".join(str(c["target_side_count"]) for c in r["copies"])
    as_ = ",".join(str(c["antibody_side_count"]) for c in r["copies"])
    print(f"{r['pdb']:6} {r['target_kind']:5} {r['copy_count']:<3} {tot:8} {ts:7} {as_:7}")

json.dump(out, open(f"{GOLD}/reference-contacts.json", "w"), ensure_ascii=False, indent=1)
print(f"\n저장: {GOLD}/reference-contacts.json")
