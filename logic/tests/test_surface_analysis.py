
import pytest

from logic import structures, surface_analysis
from logic.agent_session import CandidateSession, CandidateTools
from logic.flow import Flow, run_flow
from service.demo_input import experimental_demo
from service.live import verified_files
from logic.tests.test_flow import make_request, StubClient, CoordinateClient


def test_reference_results_keep_files_candidates_and_conditions_together(tmp_path):
    data = experimental_demo()
    data['candidates'].reverse()
    for n, c in enumerate(data['candidates']):
        c.update(candidate_id=f'renamed-{n}', name='임의 이름')
    request = make_request(data['candidates'], tmp_path)
    request['input'] = data
    output, flow = run_flow(request, client=StubClient())
    assert flow.run_status() == 'completed'
    result = output['result']
    assert len(verified_files(output, tmp_path)) == 2
    for structure in result['structures']:
        cid = structure['candidate_id']
        evidence = [e for e in result['evidence'] if e['candidate_id'] == cid]
        exposure = [e for e in evidence if e['topic'] == 'surface_exposure']
        assert len(exposure) == 2 and len({e['condition_id'] for e in exposure}) == 2
        assert all(e['measurement_state'] == 'measured' for e in exposure)
        chain = next(c['label_asym_id'] for c in structure['chain_mapping'] if c['role'] == 'target')
        assert all(r['sequence_position'] is None or 1 <= r['sequence_position'] <= 607
                   for r in structure['residue_mapping'] if r['label_asym_id'] == chain)
        assert next(e for e in evidence if e['topic'] == 'buried_sasa_sum')['value'] > 0
        assert next(e for e in evidence if e['topic'] == 'observed_glycan_protein_sasa_reduction')['value'] > 0
        for opinion in (o for o in result['opinions'] if o['candidate_id'] == cid):
            assert all(next(e for e in evidence if e['evidence_id'] == eid)['condition_id'] == opinion['condition_id']
                       for eid in opinion['evidence_ids'])


@pytest.mark.parametrize('reason', ['치료 효능이 입증되었고 부작용이 없다.', '결합 친화도는 39 nM이다.'])
def test_free_model_claims_do_not_become_reported_facts(tmp_path, reason):
    candidates = experimental_demo()['candidates']
    flow = Flow(make_request(candidates, tmp_path), client=StubClient())
    tools = CandidateTools(flow, CandidateSession(candidates[0]))
    tools.check_input(); tools.lookup_public_structure()
    tools.use_experimental_structure('서열이 일치한다.'); tools.compare_structure()
    tools.submit_opinion('needs_confirmation', reason)
    assert tools.s.terminal == 'completed'
    assert flow.opinions and all(reason not in o['reason'] for o in flow.opinions)
    assert all('결합력·치료 효능·안전성 판단이 아니다.' in ' '.join(o['limitations']) for o in flow.opinions)


def test_coordinate_identity_is_not_candidate_name_or_public_status():
    from logic.tests.test_flow import _boltz2_cif
    seq = {'target': 'ACD', 'heavy': 'EFG', 'light': 'HIK'}
    mapping = [{'role': role, 'label_asym_id': chain} for role, chain in zip(seq, ['A', 'B', 'C'])]
    text = _boltz2_cif(list(zip(['A', 'B', 'C'], seq.values())))
    result = surface_analysis.calculate(text, mapping, seq)
    assert result['core']['surface_exposure'] > 0
    assert result['core']['buried_sasa_sum'] > 0
    assert result['context'] is None and result['context_reason']
    changed = surface_analysis.calculate(text.replace('0 1 1 .', '0 1 0.5 .'), mapping, seq)
    assert changed['core'] is None and '점유율' in changed['reason']


def test_the_public_surface_results_match_the_independent_team_calculation(tmp_path):
    output, _ = run_flow(make_request(experimental_demo()['candidates'], tmp_path), client=StubClient())
    for cid, surface, buried, reduction in [('trastuzumab', 47482.87683177106, 1444.077963126554, 240.7248499315863),
                                           ('pertuzumab', 46188.26756769667, 2121.4270123028327, 426.33142017768677)]:
        rows = [e for e in output['result']['evidence'] if e['candidate_id'] == cid]
        assert next(e['value'] for e in rows if e['topic'] == 'surface_exposure' and e['condition_id'].endswith('core')) == pytest.approx(surface, rel=0, abs=1e-7)
        assert next(e['value'] for e in rows if e['topic'] == 'buried_sasa_sum') == pytest.approx(buried, rel=0, abs=1e-7)
        assert next(e['value'] for e in rows if e['topic'] == 'observed_glycan_protein_sasa_reduction') == pytest.approx(reduction, rel=0, abs=1e-7)


def test_new_sequences_receive_the_same_surface_topics(tmp_path):
    from logic.tests.test_flow import _prediction_candidates
    output, flow = run_flow(make_request(_prediction_candidates(), tmp_path), client=CoordinateClient())
    assert flow.run_status() == 'completed'
    for cid in output['result']['candidate_ids']:
        mine = [e for e in output['result']['evidence'] if e['candidate_id'] == cid]
        assert next(e for e in mine if e['topic'] == 'buried_sasa_sum')['measurement_state'] == 'measured'
        assert next(e for e in mine if e['topic'] == 'observed_glycan_protein_sasa_reduction')['measurement_state'] == 'unknown'
    assert all(s['kind'] == 'predicted' for s in output['result']['structures'])


def test_source_numbering_offset_is_not_mistaken_for_input_numbering():
    from logic.tests.test_flow import _boltz2_cif
    text = _boltz2_cif([('A', 'MACD'), ('B', 'EFG'), ('C', 'HIK')])
    mapping = [{'role': r, 'label_asym_id': c} for r, c in [('target', 'A'), ('heavy', 'B'), ('light', 'C')]]
    result = surface_analysis.calculate(text, mapping, {'target': 'ACD', 'heavy': 'EFG', 'light': 'HIK'})
    assert result['core'] is not None
    target = [r for r in result['residues'] if r['label_asym_id'] == 'A']
    assert [(r['label_seq_id'], r['sequence_position']) for r in target] == [(2, 1), (3, 2), (4, 3)]


def test_overlapping_sequence_matches_are_ambiguous():
    from logic.tests.test_flow import _boltz2_cif
    text = _boltz2_cif([('A', 'AAAA'), ('B', 'EFG'), ('C', 'HIK')])
    mapping = [{'role': r, 'label_asym_id': c} for r, c in [('target', 'A'), ('heavy', 'B'), ('light', 'C')]]
    result = surface_analysis.calculate(text, mapping, {'target': 'AAA', 'heavy': 'EFG', 'light': 'HIK'})
    assert result['core'] is None and '대응' in result['reason']


def test_inconsistent_covalent_residue_identity_withholds_context():
    import gemmi
    data = experimental_demo()
    block = gemmi.cif.read_file(str(structures.STRUCTURE_DIR / '1N8Z.cif')).sole_block()
    links = block.find('_struct_conn.', ['conn_type_id', 'ptnr1_label_asym_id', 'ptnr1_label_seq_id'])
    bond = next(r for r in links if r[0] == 'covale' and r[1] == 'C')
    bond[2] = '1'
    candidate = data['candidates'][0]
    mapping = [{'role': r, 'label_asym_id': c} for r, c in [('target', 'C'), ('heavy', 'B'), ('light', 'A')]]
    result = surface_analysis.calculate(block.as_string(), mapping, {
        'target': data['target']['fasta'], 'heavy': candidate['heavy_chain_fasta'], 'light': candidate['light_chain_fasta']})
    assert result['core'] is not None
    assert result['context'] is None and '공유결합 원자의 대응' in result['context_reason']


def test_predicting_a_known_candidate_uses_its_predicted_coordinates(tmp_path):
    candidates = experimental_demo()['candidates']
    flow = Flow(make_request(candidates, tmp_path), client=CoordinateClient())
    tools = CandidateTools(flow, CandidateSession(candidates[0]))
    tools.check_input(); tools.lookup_public_structure()
    tools.predict_structure('대조를 위한 새 예측을 선택한다.'); tools.compare_structure()
    e = next(e for e in flow.evidence if e['topic'] == 'interface_contact_residues')
    assert e['measurement_state'] == 'measured' and e['value'] != 39
    assert e['structure_id'].endswith('boltz2')
    assert all(s.get('record_id') != '1N8Z' for s in e['sources'])
