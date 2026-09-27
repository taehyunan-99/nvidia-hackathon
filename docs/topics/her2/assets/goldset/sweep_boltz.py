"""Boltz-2 설정을 바꿔 가며 예측 에피토프 F1을 잰다.

왜: of3-crosscheck 실측에서 Boltz-2는 1N8Z의 HER2쪽 접촉 19개 중 5개만 맞혔다
(재현율 0.26). 이 저장소가 쓰는 설정은 호스팅 API의 최소값이다
(`diffusion_samples=1`, `recycling_steps=3`, `sampling_steps=50`).
올리면 나아지는지 찍지 말고 재 본다.

호스팅 API는 구조 템플릿을 받지 않는다(2026-09-26 스키마 확인). MSA는
of3-crosscheck에서 HER2쪽 겹침을 5→0으로 떨어뜨려 쓰지 않는다.

**유료 호출이다.** 설정 하나에 Boltz-2 1회. `--settings`로 고른 것만 돌린다.
`diffusion_samples=N`이면 구조가 N개 오므로 전부 채점해 최고·평균을 함께 낸다.
그래야 "표본이 모자란 것인지, 모델이 못 맞히는 것인지"가 갈린다.

    python docs/topics/her2/assets/goldset/sweep_boltz.py --settings baseline,samples5
    python docs/topics/her2/assets/goldset/sweep_boltz.py --summary
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
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

from logic import contacts, structures  # noqa: E402
from logic.env import load_env  # noqa: E402
from logic.nvidia_client import NvidiaClient  # noqa: E402
from logic.tests.test_flow import TRASTUZUMAB, entity_sequence  # noqa: E402

from score_epitope import f1, remap  # noqa: E402

# of3-crosscheck와 같은 입력이라 그 결과(F1 0.349, HER2쪽 5/19)와 견줄 수 있다.
CASE = "1N8Z"

# 호스팅 API 범위: recycling 1~6, sampling 10~1000, diffusion 1~5, step_scale 0.5~5.
SETTINGS = {
    "baseline":   {"recycling_steps": 3, "sampling_steps": 50,  "diffusion_samples": 1},
    "samples5":   {"recycling_steps": 3, "sampling_steps": 50,  "diffusion_samples": 5},
    "recycle6":   {"recycling_steps": 6, "sampling_steps": 50,  "diffusion_samples": 5},
    "sampling200": {"recycling_steps": 3, "sampling_steps": 200, "diffusion_samples": 5},
    "max":        {"recycling_steps": 6, "sampling_steps": 200, "diffusion_samples": 5},
}


def reference() -> tuple[set, str]:
    """1N8Z 결정 구조의 HER2쪽 접촉 잔기와 표적 서열."""
    path = ROOT / "frontend" / "public" / "structures" / f"{CASE}.cif"
    text = path.read_text(encoding="utf-8")
    ents, _ = structures.parse_entities(text)
    target = next(e for e in ents
                  if "erbb-2" in (e.description or "").lower() or "her2" in (e.description or "").lower())
    data = json.loads((GENERATED / "reference-contacts.json").read_text(encoding="utf-8"))
    row = next(r for r in data if r["pdb"] == CASE)
    return set(row["copies"][0]["target_side_resnum"]), target.sequence


def score_prediction(cif_text: str, ref_positions: set, ref_seq: str, target_seq: str) -> dict:
    """예측 구조의 표적쪽 접촉 잔기를 1N8Z 좌표로 옮겨 채점한다.

    예측 요청에서 표적은 id 'A'로 보내지만 Boltz-2가 사슬 이름을 다시 붙인다.
    서열로 어느 사슬이 표적인지 찾는다(flow._predicted_chain_mapping와 같은 방식).
    """
    ents, _ = structures.parse_entities(cif_text)
    by_seq = {e.sequence: e.strand_ids[0] for e in ents if e.sequence and e.strand_ids}
    t_chain = by_seq.get(structures.normalize_sequence(target_seq))
    ab_chains = {c for s, c in by_seq.items() if c != t_chain}
    if not t_chain or not ab_chains:
        return {"error": f"사슬을 찾지 못했다 target={t_chain} ab={sorted(ab_chains)}"}
    atoms = contacts.parse_atoms(cif_text)
    if not atoms:
        return {"error": "원자를 읽지 못했다. 접촉 0개로 채점하지 않는다."}
    pairs = contacts.contact_residues(atoms, {t_chain}, ab_chains)
    own = sorted(n for c, n in pairs if c == t_chain)
    pred = remap(target_seq, ref_seq, own)
    out = f1(pred, ref_positions)
    out["predicted_contacts_target_side"] = len(own)
    return out


def run(name: str, params: dict, client, ref_positions, ref_seq, target, heavy, light) -> dict:
    polymers = [
        {"id": "A", "molecule_type": "protein", "sequence": target},
        {"id": "H", "molecule_type": "protein", "sequence": heavy},
        {"id": "L", "molecule_type": "protein", "sequence": light},
    ]
    started = time.time()
    response = client.predict_complex(polymers, **params)
    elapsed = round(time.time() - started, 1)
    found = response.get("structures") or []
    scores = response.get("confidence_scores")
    scores = scores if isinstance(scores, list) else [scores]
    per = []
    for i, s in enumerate(found):
        row = score_prediction(s.get("structure", ""), ref_positions, ref_seq, target)
        row["index"] = i
        row["confidence"] = scores[i] if i < len(scores) else None
        per.append(row)
    ok = [p for p in per if "error" not in p]
    best = max(ok, key=lambda p: p["f1"], default=None)
    by_conf = max(ok, key=lambda p: (p["confidence"] or -1), default=None)
    return {
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "setting": name,
        "params": params,
        "seconds": elapsed,
        "structures": len(found),
        "per_structure": per,
        # 가장 잘 맞힌 것 — 표본을 더 뽑으면 되는 문제인지 본다.
        "best_f1": best["f1"] if best else None,
        # 신뢰도로 고른 것 — 실제로 고를 수 있는 값이다.
        "picked_by_confidence_f1": by_conf["f1"] if by_conf else None,
        "mean_f1": round(sum(p["f1"] for p in ok) / len(ok), 3) if ok else None,
    }


def summarise(path: Path) -> None:
    if not path.exists():
        print("아직 기록이 없다:", path)
        return
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"{'설정':13} {'구조':4} {'최고F1':>7} {'신뢰도선택':>10} {'평균':>7} {'초':>6}")
    for r in rows:
        print(f"{r['setting']:13} {r['structures']:<4} {str(r['best_f1']):>7} "
              f"{str(r['picked_by_confidence_f1']):>10} {str(r['mean_f1']):>7} {r['seconds']:>6}")
    print()
    print("견줄 값: of3-crosscheck의 Boltz-2 실측 F1 0.349(양쪽 합산), HER2쪽 5/19.")
    print("천장: 6BGT 결정 구조가 1N8Z 대비 F1 0.923.")


def main() -> None:
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument("--settings", default="baseline,samples5",
                    help=f"쉼표로 구분. 고를 수 있는 것: {','.join(SETTINGS)}")
    ap.add_argument("--out", default="boltz-sweep.jsonl")
    ap.add_argument("--sleep", type=float, default=60.0, help="호출 사이 대기 초(429 회피)")
    ap.add_argument("--summary", action="store_true", help="돌리지 않고 기존 기록만 집계")
    args = ap.parse_args()

    path = GENERATED / args.out
    if args.summary:
        summarise(path)
        return

    names = [n.strip() for n in args.settings.split(",") if n.strip()]
    unknown = [n for n in names if n not in SETTINGS]
    if unknown:
        raise SystemExit(f"모르는 설정: {unknown}. 고를 수 있는 것: {list(SETTINGS)}")

    ref_positions, ref_seq = reference()
    target = entity_sequence(TRASTUZUMAB, "target")
    heavy = entity_sequence(TRASTUZUMAB, "heavy")
    light = entity_sequence(TRASTUZUMAB, "light")
    target = structures.normalize_sequence(target)
    heavy = structures.normalize_sequence(heavy)
    light = structures.normalize_sequence(light)
    print(f"기준 {CASE} HER2쪽 접촉 {len(ref_positions)}잔기. 입력 표적 {len(target)}·중쇄 {len(heavy)}·경쇄 {len(light)}")
    print(f"유료 Boltz-2 호출 {len(names)}회를 보낸다: {', '.join(names)}", flush=True)

    work = ROOT / "work" / "boltz-sweep"
    work.mkdir(parents=True, exist_ok=True)
    client = NvidiaClient(work_dir=work)

    for i, name in enumerate(names):
        if i:
            time.sleep(args.sleep)
        print(f"▶ {datetime.datetime.now():%H:%M:%S} {name} {SETTINGS[name]}", flush=True)
        try:
            row = run(name, SETTINGS[name], client, ref_positions, ref_seq, target, heavy, light)
        except Exception as exc:
            print(f"   실패: {type(exc).__name__}: {exc}"[:200], flush=True)
            continue
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"   구조 {row['structures']}개 최고F1={row['best_f1']} "
              f"신뢰도선택={row['picked_by_confidence_f1']} 평균={row['mean_f1']} {row['seconds']}s",
              flush=True)

    summarise(path)


if __name__ == "__main__":
    main()
