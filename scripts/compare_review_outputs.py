"""Compare fixed public-reference topic coverage without treating it as model accuracy.

Usage: python scripts/compare_review_outputs.py BEFORE/C01/observation.json AFTER/C01/observation.json
The six positive labels come from hackathon-evaluation.md section 2 and the
previously verified public calculations, not from the product's policy module.
"""
import argparse
import json
from pathlib import Path

PUBLIC_CANDIDATES = ('trastuzumab', 'pertuzumab')
EXPECTED_REVIEW = (
    ('core', {'interface_contact_residues'}),
    ('core', {'surface_exposure', 'buried_sasa_sum'}),
    ('context', {'surface_exposure', 'observed_glycan_protein_sasa_reduction'}),
)


def assess(observation):
    result = observation['result']
    passed, total = 0, 0
    for candidate in PUBLIC_CANDIDATES:
        for kind, topics in EXPECTED_REVIEW:
            total += 1
            condition = next(c for c in result['conditions'] if c['candidate_id'] == candidate and c['kind'] == kind)
            items = [e for e in result['evidence'] if e['candidate_id'] == candidate and e['condition_id'] == condition['condition_id'] and e['topic'] in topics]
            assert {e['topic'] for e in items} == topics and all(e['measurement_state'] == 'measured' for e in items), 'Positive-label input has changed'
            ids = {e['evidence_id'] for e in items}
            passed += any(o['candidate_id'] == candidate and o['condition_id'] == condition['condition_id'] and
                          o['decision'] == 'reviewable' and ids <= set(o['evidence_ids']) for o in result['opinions'])
    unavailable = {e['evidence_id'] for e in result['evidence'] if e['topic'] in {'atom_clash','whole_range_accessibility'} and e['measurement_state'] != 'measured'}
    unsafe = {eid for o in result['opinions'] if o['decision'] == 'reviewable' for eid in o['evidence_ids'] if eid in unavailable}
    return {'supported_topic_reviews': passed, 'supported_topic_labels': total,
            'unsupported_topic_approvals': len(unsafe), 'unavailable_evidence_items': len(unavailable),
            'prediction_attempts': observation['prediction_attempts'], 'live_boltz_calls': observation['boltz_network_calls']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before',type=Path);parser.add_argument('after',type=Path)
    args=parser.parse_args()
    before,after=[json.loads(p.read_text()) for p in (args.before,args.after)]
    def measured(data):
        return sorted((e['evidence_id'], e['value'], e['unit']) for e in data['result']['evidence'] if e['measurement_state']=='measured')
    assert measured(before)==measured(after), 'The policy comparison must not change measured inputs'
    print(json.dumps({'before':assess(before),'after':assess(after),'measurement_values_unchanged':True,
                      'scope':'Two known development candidates; six policy labels, not six independent biological samples or model accuracy.'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
