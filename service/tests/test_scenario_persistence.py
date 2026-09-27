"""Public scenario intake/storage with synthetic prediction transport, no live calls."""
import csv
import hashlib
import io
import json
from pathlib import Path

import gemmi
import pytest
from fastapi.testclient import TestClient

from logic import structure_sources
from logic.agent import RuleDecider
from logic.flow import run_flow
from logic.tests.test_flow import StubClient, _boltz2_cif
from service import worker
from service.demo_input import public_reference_demo, public_prediction_demo, public_hold_demo
from service.operational import create_app
from service.tests.test_live import live_service, DSN


class SyntheticPrediction(StubClient):
    def predict_complex(self, polymers, **kwargs):
        self.calls += 1
        assert kwargs['diffusion_samples'] == 2
        block = gemmi.cif.read_string(_boltz2_cif([(p['id'],p['sequence']) for p in polymers])).sole_block()
        rows = block.find('_atom_site.', ['label_asym_id','label_seq_id','Cartn_x','Cartn_y','Cartn_z'])
        for row in rows:
            n=int(row[1]); offset=0 if row[0]=='A' else 100
            row[2],row[3],row[4]=str(n%7*3+offset),str(n//7%5*3),str(n//35*3)
        text=block.as_string()
        return {'structures':[{'structure':text,'format':'mmcif'},{'structure':text,'format':'mmcif'}], 'confidence_scores':[.8,.7]}


@pytest.mark.parametrize('make', [public_reference_demo,public_prediction_demo,public_hold_demo])
def test_scenario_retains_input_evidence_and_private_files(live_service,monkeypatch,make):
    client,root=live_service
    model=SyntheticPrediction()
    sources=Path(__file__).parent/'fixtures/scenario-sources'
    monkeypatch.setattr(structure_sources,'download',lambda pdb:(sources/f'{pdb}.cif').read_bytes())
    def run(request,progress,alive):
        assert alive()
        return run_flow(request,client=model,progress=progress,decider=RuleDecider('오프라인 합성 예측 전송 검사',decisions=[],model='test'))[0]
    monkeypatch.setattr(worker,'run_process',run)
    client.post('/api/session')
    data=make()
    accepted=client.post('/api/reviews',data={'metadata':json.dumps(data)})
    assert accepted.status_code==201,accepted.text
    review_id=accepted.json()['review_id']
    rid=client.post(f'/api/reviews/{review_id}/runs',json={'request_key':'scenario-check'}).json()['run_id']
    assert worker.process_one(DSN,data_root=root,mode='live')==rid
    state=client.get(f'/api/runs/{rid}').json()
    assert state['status']=='completed',state
    result=client.get(f'/api/runs/{rid}/result').json()
    ids=[c['candidate_id'] for c in data['candidates']]
    assert result['candidate_ids']==ids and [c['candidate_id'] for c in state['candidates']]==ids
    assert client.get(f'/api/reviews/{review_id}').json()['example_id']==data['example_id']
    predicted=make!=public_reference_demo
    assert model.calls==int(predicted)
    assert len([s for s in result['structures'] if s['kind']=='predicted'])==2*int(predicted)
    if make==public_hold_demo:
        assert any(s['candidate_id']=='fab37' and s['kind']=='experimental' for s in result['structures'])
        evidence=[e for e in result['evidence'] if e['candidate_id']=='fab37']
        assert evidence and all(e['value'] is None and e['measurement_state'] in ['not_run','unknown'] for e in evidence)
    restarted=TestClient(create_app(DSN,root,mode='live'));restarted.cookies.update(client.cookies)
    assert restarted.get(f'/api/runs/{rid}/result').json()==result
    assert restarted.get(f'/api/runs/{rid}/report.json').json()=={'run':state,'result':result}
    csv.field_size_limit(10*1024*1024)
    records=list(csv.DictReader(io.StringIO(restarted.get(f'/api/runs/{rid}/report.csv').text.lstrip('\ufeff'))))
    assert records
    stranger=TestClient(create_app(DSN,root,mode='live'));stranger.post('/api/session')
    assert stranger.get(f'/api/runs/{rid}/result').status_code==404
    for artifact in result['artifacts']:
        if artifact['status']!='ready':continue
        path=f"/api/runs/{rid}/artifacts/{artifact['artifact_id']}"
        response=restarted.get(path)
        assert response.status_code==200
        assert len(response.content)==artifact['size_bytes'] and hashlib.sha256(response.content).hexdigest()==artifact['sha256']
        assert stranger.get(path).status_code==404
