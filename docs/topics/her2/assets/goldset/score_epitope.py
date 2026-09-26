"""예측 구조의 에피토프를 결정 구조 기준과 대조해 F1을 낸다.

입력은 mmCIF 텍스트와 그 안의 표적·항체 사슬. 예측이든 결정 구조든 같은
방법으로 접촉 잔기를 뽑아 1N8Z 표적 좌표로 옮긴 뒤 집합으로 비교한다.

검산: 결정 구조를 예측 자리에 넣어 본다. 같은 항체면 F1이 높고, 다른 자리를
무는 항체면 0에 가까워야 한다. 그렇지 않으면 이 채점기를 믿으면 안 된다.
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

from logic import contacts, structures  # noqa: E402


def remap(seq_from, seq_to, positions):
    sm = difflib.SequenceMatcher(None, seq_from, seq_to, autojunk=False)
    m = {}
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            m[a + k + 1] = b + k + 1
    return {m[p] for p in positions if p in m}


def epitope(cif_text, target_chains, antibody_chains, target_sequence, ref_sequence):
    """표적쪽 접촉 잔기를 ref_sequence 좌표의 집합으로 돌려준다."""
    atoms = contacts.parse_atoms(cif_text)
    pairs = contacts.contact_residues(atoms, set(target_chains), set(antibody_chains))
    own = sorted(n for c, n in pairs if c in set(target_chains))
    return remap(target_sequence, ref_sequence, own)


def f1(pred: set, gold: set):
    if not pred or not gold:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0,
                "tp": 0, "pred_n": len(pred), "gold_n": len(gold)}
    tp = len(pred & gold)
    p = tp / len(pred)
    r = tp / len(gold)
    return {"precision": round(p, 3), "recall": round(r, 3),
            "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0,
            "tp": tp, "pred_n": len(pred), "gold_n": len(gold)}


if __name__ == "__main__":
    # 검산: 이미 계산해 둔 에피토프 집합으로 채점기를 시험한다.
    canon = {k: set(v) for k, v in json.load(open(f"{GOLD}/epitopes-1n8z-coords.json")).items()}
    cases = [
        ("1N8Z를 1N8Z로 채점 (자기 자신)", "1N8Z", "1N8Z", "1.0이어야 한다"),
        ("6BGT(트라스투주맙 변이체) → 1N8Z", "6BGT", "1N8Z", "높아야 한다"),
        ("3BE1(트라스투주맙 골격) → 1N8Z", "3BE1", "1N8Z", "높아야 한다"),
        ("9L1S(퍼투주맙 변이체) → 1S78", "9L1S", "1S78", "높아야 한다"),
        ("1S78(퍼투주맙) → 1N8Z", "1S78", "1N8Z", "0이어야 한다"),
        ("5O4G(다른 자리) → 1N8Z", "5O4G", "1N8Z", "0이어야 한다"),
        ("9T3R → 1S78", "9T3R", "1S78", "부분만 겹친다"),
    ]
    print(f"{'사례':38} {'P':>6} {'R':>6} {'F1':>6}  기대")
    for label, pred, gold, expect in cases:
        s = f1(canon[pred], canon[gold])
        print(f"{label:38} {s['precision']:>6} {s['recall']:>6} {s['f1']:>6}  {expect}")
