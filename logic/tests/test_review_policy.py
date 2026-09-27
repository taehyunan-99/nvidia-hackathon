import copy

import pytest

from logic.review_policy import topic_opinions

CONDITION = {'condition_id':'core','kind':'core','structure_ids':['structure'],'gaps':['미관측 원자는 복원하지 않았다.']}


def evidence(topic, state='measured', value=1, **extra):
    return {'evidence_id':topic,'candidate_id':'candidate','condition_id':'core','structure_id':'structure',
            'topic':topic,'measurement_state':state,'value':value if state=='measured' else None,
            'unit':'residue' if state=='measured' else None,'reason':None if state=='measured' else '자료 부족',**extra}


def opinions(items,condition=None):
    return topic_opinions('candidate',condition or CONDITION,items,'규칙')


def test_measured_contact_is_reviewable_while_accessibility_is_not():
    result=opinions([evidence('interface_contact_residues'),evidence('whole_range_accessibility','unknown')])
    assert {o['topic']:o['decision'] for o in result}=={'contact':'reviewable','accessibility':'needs_confirmation'}
    assert result[0]['evidence_ids']==['interface_contact_residues']
    assert result[1]['evidence_ids']==['whole_range_accessibility']
    assert all('예측 정확도의 증명도 아니다.' in ' '.join(o['limitations']) for o in result)


@pytest.mark.parametrize('state',['unknown','not_run','failed','not_applicable'])
def test_unmeasured_contact_is_never_reviewable(state):
    assert opinions([evidence('interface_contact_residues',state)])[0]['decision']=='needs_confirmation'


def test_measured_zero_remains_a_reviewable_observation():
    result=opinions([evidence('interface_contact_residues',value=0)])
    assert result[0]['decision']=='reviewable'
    assert '결합력·치료 효능·안전성 판단이 아니다.' in ' '.join(result[0]['limitations'])


def test_incomplete_surface_group_cannot_approve_the_missing_metric():
    result=opinions([evidence('surface_exposure')])
    assert result[0]['decision']=='needs_confirmation'
    assert 'buried_sasa_sum' in ' '.join(result[0]['limitations'])


def test_all_required_surface_metrics_support_only_surface_review():
    result=opinions([evidence('surface_exposure'),evidence('buried_sasa_sum')])
    assert [(o['topic'],o['decision']) for o in result]==[('surface','reviewable')]


def test_glycan_context_does_not_approve_whole_accessibility():
    condition={**CONDITION,'kind':'context'}
    result=opinions([evidence('surface_exposure'),evidence('observed_glycan_protein_sasa_reduction'),
                     evidence('whole_range_accessibility','unknown')],condition)
    assert {o['topic']:o['decision'] for o in result}=={'glycan':'reviewable','accessibility':'needs_confirmation'}


@pytest.mark.parametrize('change',[{'candidate_id':'other'},{'condition_id':'other'},{'structure_id':'other'}])
def test_foreign_evidence_is_rejected(change):
    with pytest.raises(ValueError,match='대응'):
        opinions([evidence('interface_contact_residues',**change)])


def test_conflicting_values_require_confirmation_and_keep_both_evidence_ids():
    first=evidence('interface_contact_residues',value=1)
    second=evidence('interface_contact_residues',value=2,evidence_id='different')
    result=opinions([first,second])[0]
    assert result['decision']=='needs_confirmation'
    assert set(result['conflicting_evidence_ids'])=={'interface_contact_residues','different'}


def test_order_is_irrelevant_and_inputs_are_not_mutated():
    items=[evidence('surface_exposure'),evidence('buried_sasa_sum')]
    before=copy.deepcopy(items)
    a,b=opinions(items),opinions(list(reversed(items)))
    assert a[0]['decision']==b[0]['decision']=='reviewable'
    assert set(a[0]['evidence_ids'])==set(b[0]['evidence_ids'])
    assert items==before
