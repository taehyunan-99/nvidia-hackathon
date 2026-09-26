"""이미 저장된 예측 구조를 에피토프 채점기로 다시 채점한다. 호출 0회.

`work/of3-crosscheck/`에 of3-crosscheck(커밋 d44f9f0)가 남긴 예측이 있다.
같은 설정을 3회 반복한 것(`-r2`·`-r3`)도 있어 **결정론 주장을 직접 검증**할 수 있다.

그 문서는 "Boltz-2는 같은 입력을 세 번 보내 세 번 모두 같은 구조를 돌려줬다"고 적었다.
한편 이 저장소의 sweep(2026-09-26 23:24)은 같은 설정에서 F1 0.0을 얻었고, 아래 채점은
저장된 파일에서 0.333을 얻는다 — 세션을 넘으면 같지 않다는 뜻이다. 어느 쪽인지 파일로 확인한다.

    python docs/topics/her2/assets/goldset/score_saved_predictions.py
"""
from __future__ import annotations

import hashlib
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
sys.path.insert(0, str(HERE))

from logic import structures  # noqa: E402
from logic.tests.test_flow import TRASTUZUMAB, entity_sequence  # noqa: E402

from sweep_boltz import reference, score_prediction  # noqa: E402

def _saved_dir() -> Path:
    """예측이 저장된 폴더. worktree에서 돌리면 본체 체크아웃의 work/를 본다.

    `work/`는 git 제외라 worktree에는 따라오지 않는다. .git이 파일이면(worktree)
    거기 적힌 공용 git 디렉터리의 부모가 본체 체크아웃이다.
    """
    import subprocess
    here = ROOT / "work" / "of3-crosscheck"
    if here.is_dir():
        return here
    try:
        out = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        main_checkout = Path(out).parent
        cand = main_checkout / "work" / "of3-crosscheck"
        if cand.is_dir():
            return cand
    except (subprocess.CalledProcessError, OSError):
        pass
    return here


FILES = [
    ("boltz2", "boltz2.cif", "Boltz-2 (서비스와 같은 설정)"),
    ("boltz2-r2", "boltz2-r2.cif", "같은 설정 2회차"),
    ("boltz2-r3", "boltz2-r3.cif", "같은 설정 3회차"),
    ("boltz2_msa", "boltz2_msa.cif", "Boltz-2 + MSA"),
    ("boltz2_msa-r2", "boltz2_msa-r2.cif", "MSA 2회차"),
    ("boltz2_msa-r3", "boltz2_msa-r3.cif", "MSA 3회차"),
    ("openfold3_msa", "openfold3_msa.cif", "OpenFold3 + MSA"),
]


def main() -> None:
    SAVED = _saved_dir()
    if not SAVED.is_dir():
        raise SystemExit(f"저장된 예측이 없다: {SAVED}\n"
                         "of3-crosscheck를 돌린 체크아웃에서 실행해야 한다(work/는 git 제외).")
    print(f"읽는 곳: {SAVED}")
    ref_pos, ref_seq = reference()
    target = structures.normalize_sequence(entity_sequence(TRASTUZUMAB, "target"))
    print(f"기준 1N8Z HER2쪽 접촉 {len(ref_pos)}잔기\n")
    print(f"{'이름':16} {'F1':>6} {'정밀':>6} {'재현':>6} {'맞춘':>7} {'예측접촉':>8}  sha256[:8]")
    rows = []
    for name, fn, label in FILES:
        path = SAVED / fn
        if not path.exists():
            print(f"{name:16} (파일 없음)")
            continue
        text = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        s = score_prediction(text, ref_pos, ref_seq, target)
        if "error" in s:
            print(f"{name:16} 오류 {s['error']}")
            continue
        s.update({"name": name, "label": label, "sha256": digest})
        rows.append(s)
        print(f"{name:16} {s['f1']:>6} {s['precision']:>6} {s['recall']:>6} "
              f"{str(s['tp']) + '/' + str(s['gold_n']):>7} "
              f"{s['predicted_contacts_target_side']:>8}  {digest[:8]}")

    print()
    for group, prefix in (("MSA 없음", "boltz2"), ("MSA 있음", "boltz2_msa")):
        same = [r for r in rows if r["name"] == prefix or r["name"].startswith(prefix + "-r")]
        if len(same) < 2:
            continue
        digests = {r["sha256"] for r in same}
        f1s = [r["f1"] for r in same]
        verdict = "같은 파일" if len(digests) == 1 else f"서로 다른 파일 {len(digests)}종"
        print(f"{group} 반복 {len(same)}회: {verdict}, F1 {f1s}")

    (GENERATED / "saved-predictions-score.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {GENERATED}/saved-predictions-score.json")


if __name__ == "__main__":
    main()
