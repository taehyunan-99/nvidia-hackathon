"""Fixed deposited sequences and source-specific branches, without model calls."""
import hashlib
import json
from pathlib import Path

import gemmi
import pytest

from logic import structure_sources, structures
from logic.contract import validate
from logic.flow import run_flow
from logic.tests.test_flow import StubClient, make_request
from logic.nvidia_client import CallFailed
from service.demo_input import public_prediction_demo, public_hold_demo

ROOT = Path(__file__).resolve().parents[2]
SOURCES = Path(__file__).parent / 'fixtures/scenario-sources'


@pytest.mark.parametrize('name,make,count',[
    ('public-prediction',public_prediction_demo,2),('public-hold',public_hold_demo,3),
])
def test_shipped_scenarios_use_complete_deposited_sequences(name,make,count):
    data=make()
    validate(data,'ReviewInput')
    assert data==json.loads((ROOT/f'docs/frontend-hosting/fixtures/{name}-input.json').read_text())
    assert len(data['candidates'])==count and data['target']['analysis_range'] is None
    assert len(structures.sequence_body(data['target']['fasta']))==607
    manifest=json.loads((ROOT/'service/demo_sequences.json').read_text())
    for c,pdb,h,l in zip(data['candidates'][1:],['6BHZ','3N85'],['1','3'],['2','2']):
        path=SOURCES/f'{pdb}.cif'
        assert hashlib.sha256(path.read_bytes()).hexdigest()==manifest[pdb]['sha256']
        block=gemmi.cif.read_file(str(path)).sole_block()
        seq={r[0]:structures.sequence_body(gemmi.cif.as_string(r[1])) for r in block.find('_entity_poly.',['entity_id','pdbx_seq_one_letter_code_can'])}
        assert seq==manifest[pdb]['entities']
        assert structures.sequence_body(c['heavy_chain_fasta'])==seq[h]
        assert structures.sequence_body(c['light_chain_fasta'])==seq[l]
        assert c['heavy_analysis_range'] is None and c['light_analysis_range'] is None
    wt,variant=data['candidates'][:2]
    assert structures.sequence_body(variant['heavy_chain_fasta'])==structures.sequence_body(wt['heavy_chain_fasta'])+'KSCDK'
    assert [(i,a,b) for i,(a,b) in enumerate(zip(structures.sequence_body(wt['light_chain_fasta']),structures.sequence_body(variant['light_chain_fasta'])),1) if a!=b]==[(185,'D','A')]


def test_real_antibody_only_predicts_and_fab37_preserves_structure_but_holds_calculations(monkeypatch,tmp_path):
    monkeypatch.setattr(structure_sources,'download',lambda pdb:(SOURCES/f'{pdb}.cif').read_bytes())
    data=public_hold_demo()
    match=structure_sources.lookup(data['candidates'][1],data['target']['fasta'],tmp_path)
    assert match.heavy_exact and match.light_exact and not match.complete and not match.blocked_reason
    match=structure_sources.lookup(data['candidates'][2],data['target']['fasta'],tmp_path)
    assert match.complete and '부분 점유율' in match.calculation_hold_reason
    request=make_request(data['candidates'],tmp_path)
    request['input']=data
    client=StubClient(error=CallFailed('Offline prediction failure, not a real Boltz response'))
    output,flow=run_flow(request,client=client)
    assert client.calls==1 and flow.run_status()=='partial'
    result=output['result']
    assert any(s['candidate_id']=='fab37' and s['kind']=='experimental' for s in result['structures'])
    evidence=[e for e in result['evidence'] if e['candidate_id']=='fab37']
    assert evidence and not any(e['measurement_state']=='measured' for e in evidence)
    for e in evidence:
        assert e['value'] is None
    contact=next(e for e in evidence if e['topic']=='interface_contact_residues')
    assert contact['measurement_state']=='not_run'
    assert '부분 점유율' in contact['reason']
