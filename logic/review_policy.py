"""Topic-scoped review availability, not antibody efficacy or prediction accuracy."""
from collections import Counter

TOPICS = {
    'contact': ('접촉 부위', ('interface_contact_residues',), '누락 좌표가 접촉 위치 검토에 영향을 주는가?'),
    'surface': ('관측 단백질 표면', ('surface_exposure', 'buried_sasa_sum'), '누락 원자가 표면과 매몰 면적을 얼마나 바꿀 수 있는가?'),
    'glycan': ('관측 당의 표면 영향', ('surface_exposure', 'observed_glycan_protein_sasa_reduction'), '관측되지 않은 당쇄까지 포함하면 표면 차이가 달라지는가?'),
    'clash': ('원자 간 충돌', ('atom_clash',), '충돌 판정에 필요한 원자 선택과 계산 기준이 마련됐는가?'),
    'accessibility': ('전체 구간 접근성', ('whole_range_accessibility',), '미관측 당쇄·주변 단백질·막 환경을 확인할 자료가 있는가?'),
    'confidence': ('모델 신뢰도 기록', ('prediction_confidence',), '독립 실험 구조와 비교했을 때 예측 위치가 실제로 맞는가?'),
    'pose': ('예측 간 자세 차이', ('pose_consistency',), '같은 입력의 표본 간 차이이며 독립 실험 구조에 대한 정확도와 구별했는가?'),
}
BOUNDARY = '선택한 구조와 계산 항목에 한정한 검토다. 결합력·치료 효능·안전성 판단이 아니다. 예측 정확도의 증명도 아니다.'


def topic_opinions(candidate_id, condition, evidence, attribution):
    """Keep missing/conflicting topics separate; never make a global approval."""
    if any(e['candidate_id'] != candidate_id or e['condition_id'] != condition['condition_id'] or
           e['structure_id'] not in condition['structure_ids'] for e in evidence):
        raise ValueError('의견 근거의 후보·조건·구조 대응이 일치하지 않는다.')
    definitions = {k:v for k,v in TOPICS.items()
                   if k != ('surface' if condition['kind'] == 'context' else 'glycan')}
    covered = {t for _,topics,_ in definitions.values() for t in topics}
    for e in evidence:
        if e['topic'] not in covered:
            definitions[e['topic']] = (e['topic'], (e['topic'],), '이 계산의 적용 범위와 독립 근거를 확인했는가?')
    opinions = []
    for topic, (label, required, question) in definitions.items():
        items = [e for e in evidence if e['topic'] in required]
        if not items:
            continue
        counts = Counter(e['topic'] for e in items)
        absent = [t for t in required if counts[t] == 0]
        duplicate = any(n > 1 for n in counts.values())
        missing = [e for e in items if e['measurement_state'] != 'measured']
        ready = not absent and not duplicate and not missing
        observed_clash = topic == 'clash' and any(e['measurement_state'] == 'measured' and e['value'] > 0 for e in items)
        if observed_clash:
            ready = False
        conflicts = [e['evidence_id'] for e in items if len({
            (other['measurement_state'], other['value'], other['unit']) for other in items
            if other['topic'] == e['topic']}) > 1]
        limitations = [e['reason'] for e in missing if e['reason']]
        if absent:
            limitations.append('필요한 계산 근거가 누락됐다: ' + ', '.join(absent))
        if duplicate:
            limitations.append('같은 항목에 여러 근거가 있어 하나의 판정으로 합치지 않았다.')
        if observed_clash:
            limitations.append('관측 구조에 비결합 원자 겹침이 있어 해당 위치를 확인해야 한다. 후보의 생물학적 부적합을 뜻하지 않는다.')
        explanation = f'{label}: 선택한 좌표에서 확인한 해당 계산 근거를 검토할 수 있다.' if ready else f'{label}: 이 항목의 판단에 필요한 근거를 추가 확인해야 한다.'
        opinions.append({
            'opinion_id': f"op-{candidate_id}-{condition['kind']}-{topic}",
            'candidate_id': candidate_id, 'condition_id': condition['condition_id'], 'topic': topic,
            'decision': 'reviewable' if ready else 'needs_confirmation',
            'evidence_ids': [e['evidence_id'] for e in items], 'conflicting_evidence_ids': conflicts,
            'reason': f'{explanation} (판단: 규칙 — 항목별 근거; 진행: {attribution})',
            'limitations': list(dict.fromkeys(limitations + condition['gaps'] + [BOUNDARY])),
            'follow_up_questions': [question],
        })
    return opinions
