"""같은 입력으로 나온 5개 예측이 서로 같은 자리에 붙는지 잰다. API를 부르지 않는다.

    python docs/topics/her2/assets/goldset/check_sample_agreement.py

왜 쟀는가: 8JYR이 왜 실패했는지 항체 CDR 위치로는 구분되지 않았다. 정답을
모르는 상태에서도 쓸 수 있는 신호가 필요했다. 같은 입력을 5번 돌려 나온 구조가
서로 다른 자리에 붙으면 그 예측은 못 믿는다는 가설이었다.

결과: 가설은 틀렸다. 맞은 사례(1N8Z)와 틀린 사례(1S78) 모두 샘플 간 일치도가
바닥이어서 둘을 가르지 못한다. 대신 그 과정에서 나온 사실을 남긴다 — 5개
샘플은 서로 완전히 다른 자리에 붙고, 공통 잔기가 하나도 없다. 예측이 에피토프를
정하지 못한다는 뜻이다. 자세한 해석은 docs/topics/her2/agent-performance-validation.md.

한계: 5샘플 캐시 응답은 1N8Z·1S78 두 건뿐이다. 8JYR·3N85는 diffusion_samples=1로
돌려서 이 지표를 잴 수 없다. 사례 2건·샘플 10개로는 임계값을 정할 수 없다.
"""
import hashlib
import itertools
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(ROOT))

from logic import analysis, contacts, structures  # noqa: E402
from logic.tests.test_flow import entity_sequence  # noqa: E402

# 후보 항체가 트라스투주맙 자신인지. 1N8Z는 자기 자신이라 맞히는 게 정상이다.
CASES = {"1N8Z": True, "1S78": False}
# 실험 구조에서 표적(HER2)이 붙은 사슬. contacts.json의 잔기 번호가 이 사슬 기준이다.
EXPERIMENTAL_TARGET_CHAIN = {"1N8Z": "C", "1S78": "A"}


def mapping_for(cif_text: str, target_sequence: str) -> dict:
    """서열로 표적·항체 사슬을 찾는다(flow._predicted_chain_mapping과 같은 방식)."""
    entities, _ = structures.parse_entities(cif_text)
    by_seq = {structures.normalize_sequence(e.sequence): e.strand_ids[0]
              for e in entities if e.sequence and e.strand_ids}
    target = by_seq.get(structures.normalize_sequence(target_sequence))
    others = sorted(c for c in by_seq.values() if c != target)
    if target is None or len(others) != 2:
        raise SystemExit(f"사슬을 찾지 못했다 target={target} others={others}")
    return {"target": target, "antibody": set(others)}


def epitope(cif_text: str, target_sequence: str) -> set[int]:
    """예측 구조의 표적 쪽 접촉 잔기 번호. 실험 쪽과 같은 기준으로 센다."""
    roles = mapping_for(cif_text, target_sequence)
    atoms = contacts.parse_atoms(cif_text)
    return {n for c, n in contacts.contact_residues(atoms, {roles["target"]}, roles["antibody"])
            if c == roles["target"]}


def jaccard(a: set[int], b: set[int]) -> float:
    union = a | b
    return round(len(a & b) / len(union), 3) if union else 0.0


def experimental_epitope(pid: str) -> set[int]:
    """그 사례 자신의 실험 계면. contacts.json에 팀이 미리 계산해 둔 값이다."""
    entry = analysis._contacts().get(pid) or {}
    chain = EXPERIMENTAL_TARGET_CHAIN[pid]
    return {r["seq"] for r in entry.get("residues", []) if r["chain"] == chain}


def single_sample_epitope(pid: str, target_sequence: str) -> tuple[set[int], str]:
    """diffusion_samples=1로 따로 돌린 실행. 5샘플 선택 결과와 견주려고 같이 읽는다."""
    path = next((ROOT / "work/quality" / f"{pid}-1").glob("st-*.cif"))
    text = path.read_text()
    return epitope(text, target_sequence), path.name


def measure(pid: str) -> dict:
    work = ROOT / "work/quality" / f"{pid}-5"
    response = json.loads((work / "boltz2_response.json").read_text())
    found = response["structures"]
    conf = response.get("confidence_scores") or [None] * len(found)
    iptm = response.get("iptm_scores") or [None] * len(found)
    target_seq = entity_sequence(pid, "target")
    truth = experimental_epitope(pid)
    single, single_file = single_sample_epitope(pid, target_seq)

    samples = []
    for index, item in enumerate(found):
        text = item["structure"]
        own = epitope(text, target_seq)
        samples.append({
            "index": index,
            "source": item.get("source"),
            "confidence_score": conf[index] if index < len(conf) else None,
            "iptm_score": iptm[index] if index < len(iptm) else None,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "contact_residues": sorted(own),
            "contact_count": len(own),
            "agreement_with_experiment": jaccard(own, truth),
            "experimental_residues_recovered": len(own & truth),
            "same_epitope_as_single_sample_run": sorted(own) == sorted(single),
        })

    ranked = sorted(samples, key=lambda s: (s["confidence_score"] is not None,
                                            s["confidence_score"] or 0), reverse=True)
    best_by_confidence = ranked[0]
    best_by_truth = max(samples, key=lambda s: s["agreement_with_experiment"])
    sets = [set(s["contact_residues"]) for s in samples]
    pairs = [{"a": samples[i]["source"], "b": samples[j]["source"],
              "jaccard": jaccard(sets[i], sets[j])}
             for i, j in itertools.combinations(range(len(sets)), 2)]
    values = [p["jaccard"] for p in pairs]
    union = set().union(*sets) if sets else set()
    shared = set.intersection(*sets) if sets else set()
    return {
        "case": pid,
        "candidate_is_trastuzumab": CASES[pid],
        "diffusion_samples": len(found),
        "mean_pairwise_agreement": round(sum(values) / len(values), 3) if values else None,
        "min_pairwise_agreement": min(values) if values else None,
        "max_pairwise_agreement": max(values) if values else None,
        "residues_in_every_sample": sorted(shared),
        "residues_in_any_sample": len(union),
        "consensus_fraction": round(len(shared) / len(union), 3) if union else None,
        "experimental_epitope_size": len(truth),
        "selected_by_confidence": best_by_confidence["source"],
        "selected_agreement_with_experiment": best_by_confidence["agreement_with_experiment"],
        "closest_to_experiment": best_by_truth["source"],
        "closest_agreement_with_experiment": best_by_truth["agreement_with_experiment"],
        "confidence_rank_picks_closest": best_by_confidence["source"] == best_by_truth["source"],
        "confidence_margin_over_runner_up": (
            round(ranked[0]["confidence_score"] - ranked[1]["confidence_score"], 4)
            if len(ranked) > 1 and None not in (ranked[0]["confidence_score"],
                                                ranked[1]["confidence_score"]) else None),
        "single_sample_run_file": single_file,
        "single_sample_matches_selected": (
            sorted(single) == best_by_confidence["contact_residues"]),
        "samples": samples,
        "pairwise": pairs,
    }


def main() -> None:
    rows = [measure(pid) for pid in CASES]
    out = {
        "definition": (
            "같은 입력으로 나온 예측 구조들의 표적 쪽 접촉 잔기 집합을 짝마다 자카드로 "
            "견준 평균이다. 정답을 몰라도 잴 수 있다는 것이 이 지표를 시험한 이유다."
        ),
        "verdict": (
            "지표로 쓸 수 없다. 맞은 사례(1N8Z)와 틀린 사례(1S78) 모두 평균 일치도가 "
            "0.05 이하이고 모든 샘플에 공통인 잔기가 0개여서 둘을 가르지 못한다."
        ),
        "note": ("캐시된 응답만 쓴다. 새 API 호출 0회. 5샘플 응답이 있는 사례는 "
                 "1N8Z·1S78뿐이라 8JYR·3N85는 여기서 잴 수 없다. 사례 2건·샘플 10개로 "
                 "임계값을 정하지 않는다."),
        "cases": rows,
    }
    (HERE / "generated/sample-agreement-check.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(out["verdict"], "\n")
    for r in rows:
        print(f"===== {r['case']} (후보=트라스투주맙: {r['candidate_is_trastuzumab']}) "
              f"실험 에피토프 {r['experimental_epitope_size']}개")
        print(f"  평균 일치도 {r['mean_pairwise_agreement']} / 최대 {r['max_pairwise_agreement']} "
              f"/ 모든 샘플 공통 잔기 {len(r['residues_in_every_sample'])}개")
        print(f"  신뢰도 1위={r['selected_by_confidence']} (vs실험 {r['selected_agreement_with_experiment']}), "
              f"실험에 제일 가까운 샘플={r['closest_to_experiment']} "
              f"(vs실험 {r['closest_agreement_with_experiment']}) "
              f"→ 일치 {r['confidence_rank_picks_closest']}")
        print(f"  1위-2위 신뢰도 차 {r['confidence_margin_over_runner_up']}, "
              f"1샘플 실행이 5샘플 선택과 같은가: {r['single_sample_matches_selected']}")
        for s in sorted(r["samples"], key=lambda s: -s["confidence_score"]):
            print(f"    {s['source']:<24} n={s['contact_count']:<3} conf={s['confidence_score']:.4f} "
                  f"iptm={s['iptm_score']:.4f} vs실험 J={s['agreement_with_experiment']:<6} "
                  f"복원 {s['experimental_residues_recovered']}/{r['experimental_epitope_size']}")
        print()


if __name__ == "__main__":
    main()
