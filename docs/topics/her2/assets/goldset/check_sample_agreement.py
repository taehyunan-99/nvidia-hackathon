"""같은 입력으로 나온 5개 예측이 서로, 그리고 실험 계면과 얼마나 맞는지 잰다.

    python docs/topics/her2/assets/goldset/check_sample_agreement.py

API를 부르지 않는다. 캐시된 5샘플 응답만 읽는다. 8JYR 응답을 새로 받으려면
`fetch_benchmark_samples.py --case 8JYR --samples 5`를 먼저 돌린다(유료 1회).

왜 쟀는가: 8JYR이 왜 실패했는지 항체 CDR 위치로는 못 가렸다. 정답을 몰라도
쓸 수 있는 신호로 **샘플 간 에피토프 일치도**를 시험했다.

결과 1 — 그 가설은 틀렸다. 맞은 사례(1N8Z 0.050)와 틀린 사례(1S78 0.005,
8JYR 0.104) 모두 일치도가 바닥이고 모든 샘플에 공통인 잔기가 세 사례 다 0개다.
임계값을 그을 자리가 없어 지표에서 내린다.

결과 2 — 대신 **신뢰도 순위가 에피토프 정확도를 거스른다**는 것이 3사례에서
보인다. 자세한 해석은 docs/topics/her2/agent-performance-validation.md.
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

MANIFEST = HERE / "generated/agent-benchmark-manifest.json"
# 후보 항체가 트라스투주맙 자신인지. 1N8Z는 자기 자신이라 맞히는 게 정상이다.
IS_TRASTUZUMAB = {"1N8Z": True, "1S78": False, "8JYR": False}
# catalog 사례의 실험 표적 사슬(label). contacts.json의 잔기 번호가 이 기준이다.
CATALOG_TARGET_CHAIN = {"1N8Z": "C", "1S78": "A"}


def predicted_epitope(cif_text: str, target_sequence: str) -> set[int]:
    """예측 구조의 표적 쪽 접촉 잔기. 서열로 사슬을 찾는다(flow와 같은 방식)."""
    entities, _ = structures.parse_entities(cif_text)
    by_seq = {structures.normalize_sequence(e.sequence): e.strand_ids[0]
              for e in entities if e.sequence and e.strand_ids}
    target = by_seq.get(structures.normalize_sequence(target_sequence))
    antibody = {c for c in by_seq.values() if c != target}
    if target is None or len(antibody) != 2:
        raise SystemExit(f"예측 구조에서 사슬을 찾지 못했다 target={target} 나머지={antibody}")
    atoms = contacts.parse_atoms(cif_text)
    return {n for c, n in contacts.contact_residues(atoms, {target}, antibody) if c == target}


def catalog_case(pid: str) -> tuple[str, set[int]]:
    """1N8Z·1S78. 실험 계면은 팀이 미리 계산해 둔 contacts.json을 그대로 쓴다."""
    entry = analysis._contacts().get(pid) or {}
    chain = CATALOG_TARGET_CHAIN[pid]
    truth = {r["seq"] for r in entry.get("residues", []) if r["chain"] == chain}
    return entity_sequence(pid, "target"), truth


def benchmark_case(pid: str) -> tuple[str, set[int]]:
    """8JYR·3N85. catalog에 없어서 원본 구조에서 실험 계면을 직접 센다.

    `parse_entities`가 주는 strand_ids는 auth 사슬이고 좌표는 label 사슬이다.
    8JYR은 auth H·L이 label B·C여서 그대로 쓰면 접촉이 0개로 나온다.
    """
    import gemmi

    case = next(c for c in json.loads(MANIFEST.read_text())["cases"] if c["id"] == pid)
    sequences = {r: structures.normalize_sequence(s) for r, s in case["sequences"].items()}
    source = ROOT / "work/agent-benchmark/sources" / f"{pid}.cif"
    text = source.read_text(encoding="utf-8")

    st = gemmi.read_structure(str(source))
    st.setup_entities()
    auth_to_label = {ch.name: ch.get_polymer().subchain_id()
                     for ch in st[0] if len(ch.get_polymer())}
    entities, _ = structures.parse_entities(text)
    role_label = {}
    for entity in entities:
        normalized = structures.normalize_sequence(entity.sequence)
        for role, full in sequences.items():
            if normalized == full and entity.strand_ids:
                role_label[role] = auth_to_label[entity.strand_ids[0]]
    if set(role_label) != {"target", "heavy", "light"}:
        raise SystemExit(f"{pid} 원본에서 표적·중쇄·경쇄를 모두 찾지 못했다: {role_label}")
    atoms = contacts.parse_atoms(text)
    antibody = {role_label["heavy"], role_label["light"]}
    truth = {n for c, n in contacts.contact_residues(atoms, {role_label["target"]}, antibody)
             if c == role_label["target"]}
    return sequences["target"], truth


LOADERS = {"1N8Z": catalog_case, "1S78": catalog_case, "8JYR": benchmark_case}


def jaccard(a: set[int], b: set[int]) -> float:
    union = a | b
    return round(len(a & b) / len(union), 3) if union else 0.0


def measure(pid: str) -> dict | None:
    work = ROOT / "work/quality" / f"{pid}-5"
    path = work / "boltz2_response.json"
    if not path.exists():
        return None
    response = json.loads(path.read_text())
    found = response["structures"]
    conf = response.get("confidence_scores") or [None] * len(found)
    iptm = response.get("iptm_scores") or [None] * len(found)
    target_seq, truth = LOADERS[pid](pid)

    samples = []
    for index, item in enumerate(found):
        text = item["structure"]
        own = predicted_epitope(text, target_seq)
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
        })

    ranked = sorted(samples, key=lambda s: s["confidence_score"] or 0, reverse=True)
    for rank, sample in enumerate(ranked, start=1):
        sample["confidence_rank"] = rank
    picked = ranked[0]
    closest = max(samples, key=lambda s: s["agreement_with_experiment"])
    sets = [set(s["contact_residues"]) for s in samples]
    pairs = [{"a": samples[i]["source"], "b": samples[j]["source"],
              "jaccard": jaccard(sets[i], sets[j])}
             for i, j in itertools.combinations(range(len(sets)), 2)]
    values = [p["jaccard"] for p in pairs]
    union = set().union(*sets)
    shared = set.intersection(*sets)
    return {
        "case": pid,
        "candidate_is_trastuzumab": IS_TRASTUZUMAB[pid],
        "diffusion_samples": len(found),
        "experimental_epitope_size": len(truth),
        "experimental_epitope": sorted(truth),
        "mean_pairwise_agreement": round(sum(values) / len(values), 3) if values else None,
        "min_pairwise_agreement": min(values) if values else None,
        "max_pairwise_agreement": max(values) if values else None,
        "residues_in_every_sample": sorted(shared),
        "residues_in_any_sample": len(union),
        "selected_by_confidence": picked["source"],
        "selected_agreement_with_experiment": picked["agreement_with_experiment"],
        "closest_to_experiment": closest["source"],
        "closest_confidence_rank": closest["confidence_rank"],
        "closest_agreement_with_experiment": closest["agreement_with_experiment"],
        "confidence_rank_picks_closest": picked["source"] == closest["source"],
        "samples": samples,
        "pairwise": pairs,
    }


def main() -> None:
    rows = [r for r in (measure(pid) for pid in LOADERS) if r]
    missing = [pid for pid in LOADERS if not (ROOT / "work/quality" / f"{pid}-5").exists()]
    out = {
        "definition": (
            "같은 입력으로 나온 예측 구조들의 표적 쪽 접촉 잔기 집합을 짝마다 자카드로 "
            "견준 평균이다. 정답을 몰라도 잴 수 있다는 것이 이 지표를 시험한 이유다."
        ),
        "verdict_sample_agreement": (
            "지표로 쓸 수 없다. 맞은 사례와 틀린 사례 모두 평균 일치도가 낮고 모든 샘플에 "
            "공통인 잔기가 0개여서 둘을 가르지 못한다."
        ),
        "observation_confidence_rank": (
            "신뢰도 1위가 실험 계면에 제일 가까운 샘플인 경우는 트라스투주맙(1N8Z) 한 건뿐이다. "
            "1S78은 1위가 겹침 0이고 4위가 제일 가까웠으며, 8JYR은 1·2·3위가 모두 겹침 0이고 "
            "4·5위만 실험 계면에 닿았다. 사례 3건이라 규칙이 아니라 관측으로 적는다."
        ),
        "note": "캐시된 응답만 쓴다. 새 API 호출 0회.",
        "cases_without_cached_response": missing,
        "cases": rows,
    }
    (HERE / "generated/sample-agreement-check.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(out["verdict_sample_agreement"], "\n")
    for r in rows:
        print(f"===== {r['case']} (후보=트라스투주맙: {r['candidate_is_trastuzumab']}) "
              f"실험 에피토프 {r['experimental_epitope_size']}개")
        print(f"  샘플 간 평균 일치도 {r['mean_pairwise_agreement']} / 최대 "
              f"{r['max_pairwise_agreement']} / 모든 샘플 공통 잔기 "
              f"{len(r['residues_in_every_sample'])}개")
        print(f"  신뢰도 1위가 실험에 제일 가까운가: {r['confidence_rank_picks_closest']} "
              f"(제일 가까운 샘플은 신뢰도 {r['closest_confidence_rank']}위, "
              f"J={r['closest_agreement_with_experiment']})")
        for s in sorted(r["samples"], key=lambda s: s["confidence_rank"]):
            print(f"    {s['confidence_rank']}위 {s['source']:<24} n={s['contact_count']:<3} "
                  f"conf={s['confidence_score']:.4f} iptm={s['iptm_score']:.4f} "
                  f"vs실험 J={s['agreement_with_experiment']:<6} "
                  f"복원 {s['experimental_residues_recovered']}/{r['experimental_epitope_size']}")
        print()
    if missing:
        print("5샘플 응답이 없어 재지 못한 사례:", ", ".join(missing))


if __name__ == "__main__":
    main()
