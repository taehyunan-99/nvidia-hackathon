"""Supplied provenance is a retrieval hint, never proof of candidate identity."""
import copy

import pytest
import requests

from logic import analysis, structure_sources as sources
from logic.agent_session import CandidateSession, CandidateTools, allowed_tools
from logic.flow import Flow, run_flow
from logic.tests.test_flow import _boltz2_cif, candidate, make_request, StubClient

DOWNLOAD = sources.download


def cif(chains=None, pdb='1ABC'):
    chains = chains or [('T','AACDE'), ('H','FGHI'), ('L','KLMN')]
    text = _boltz2_cif(chains).replace('data_predicted',f'data_{pdb}\n_entry.id {pdb}\n_exptl.method \'X-RAY DIFFRACTION\'')
    text = text.replace('_atom_site.label_alt_id\n','_atom_site.label_alt_id\n_atom_site.auth_asym_id\n')
    return '\n'.join(line + ' author-' + line.split()[0] if ' C CA ' in line else line for line in text.splitlines()) + '\n'


def input_candidate(pdb='1ABC'):
    value = candidate('sample','arbitrary name','FGHI','KLMN')
    value['sources']=[{'title':'reference','record_id':pdb,'url':f'https://www.rcsb.org/structure/{pdb}'}]
    return value


@pytest.fixture(autouse=True)
def no_unexpected_download(monkeypatch):
    def unexpected(pdb):
        raise AssertionError(f'Unexpected download {pdb}')
    monkeypatch.setattr(sources,'download',unexpected)


@pytest.mark.parametrize('source',[
    {'record_id':'1ABC','url':'https://www.rcsb.org/structure/2ABC'},
    {'record_id':'1ABC','url':'http://127.0.0.1/1ABC'},
    {'record_id':'1ABC','url':'https://files.rcsb.org.evil.test/download/1ABC.cif'},
    {'record_id':'1ABC','url':'https://user@www.rcsb.org/structure/1ABC'},
    {'record_id':'1ABC','url':'https://www.rcsb.org:8443/structure/1ABC'},
    {'record_id':'not-a-pdb','url':'https://www.rcsb.org/structure/1ABC'},
])
def test_conflicting_or_untrusted_provenance_is_held_without_network(source,tmp_path):
    c=input_candidate();c['sources']=[source]
    result=sources.lookup(c,'ACD',tmp_path)
    assert result.blocked_reason and not result.complete


def test_label_chains_and_input_range_are_verified_and_cached(monkeypatch,tmp_path):
    calls=[]
    def download(pdb):calls.append(pdb);return cif().encode()
    monkeypatch.setattr(sources,'download',download)
    first=sources.lookup(input_candidate(),'ACD',tmp_path)
    assert first.complete and not first.blocked_reason
    assert [m['label_asym_id'] for m in first.chain_mapping]==['T','H','L']
    assert [m['auth_asym_id'] for m in first.chain_mapping]==['author-T','author-H','author-L']
    assert first.residue_ranges[0]==('T',2,4)
    c=input_candidate();c['name']='changed';c['candidate_id']='other'
    second=sources.lookup(c,'ACD',tmp_path)
    assert second.chain_mapping==first.chain_mapping and calls==['1ABC']
    first.public.path.write_text('tampered')
    assert '무결성' in sources.lookup(c,'ACD',tmp_path).blocked_reason


def test_parent_reference_does_not_become_variant_structure(monkeypatch,tmp_path):
    monkeypatch.setattr(sources,'download',lambda pdb:cif().encode())
    c=input_candidate();c['heavy_chain_fasta']='AGHI'
    result=sources.lookup(c,'ACD',tmp_path)
    assert not result.complete and not result.blocked_reason
    assert not result.heavy_exact and result.light_exact
    assert '부모' in result.notes[0]


@pytest.mark.parametrize('content,reason',[
    (cif(pdb='2ABC'),'식별자'),
    (cif().replace("'X-RAY DIFFRACTION'","'THEORETICAL MODEL'"),'실험 구조'),
    (cif().replace('T 1 2 ALA','T 1 2 GLY'),'잔기 종류'),
    (cif().replace('20 3 0 1','nan 3 0 1'),'유한하지'),
    (cif().replace('20 3 0 1','20 3 0 2'),'모델'),
    (cif([('T','AACDE'),('H','FGHI'),('L','KLMN'),('W','KLMN')]),'여러 개'),
    (cif().replace('AACDE','VVVVV').replace('T 1 1 ALA','T 1 1 VAL'),'표적 서열'),
])
def test_invalid_structure_cannot_be_ready(monkeypatch,tmp_path,content,reason):
    monkeypatch.setattr(sources,'download',lambda pdb:content.encode())
    result=sources.lookup(input_candidate(),'ACD',tmp_path)
    assert not result.complete and reason in result.blocked_reason


def test_duplicate_label_copy_is_not_silently_selected(monkeypatch,tmp_path):
    text=cif().replace('H 2\n','H 2\nJ 2\n')
    monkeypatch.setattr(sources,'download',lambda pdb:text.encode())
    result=sources.lookup(input_candidate(),'ACD',tmp_path)
    assert '복사체' in result.blocked_reason


def test_multiple_complete_sources_require_a_selection(monkeypatch,tmp_path):
    monkeypatch.setattr(sources,'download',lambda pdb:cif(pdb=pdb).encode())
    c=input_candidate();c['sources']+=input_candidate('2ABC')['sources']
    assert '구조가 여러 개' in sources.lookup(c,'ACD',tmp_path).blocked_reason


def test_fetch_failure_is_not_a_no_match_or_prediction(monkeypatch,tmp_path):
    def timeout(pdb):raise requests.Timeout()
    monkeypatch.setattr(sources,'download',timeout)
    c=input_candidate();c.update(heavy_chain_fasta='A'*60,light_chain_fasta='C'*60)
    request=make_request([c,replace_candidate(c)],tmp_path)
    client=StubClient(error=AssertionError('must not predict on failed lookup'))
    _,flow=run_flow(request,client=client)
    assert flow.run_status()=='partial' and client.calls==0
    f=Flow(request,client=client);s=CandidateSession(c);t=CandidateTools(f,s)
    t.check_input();t.lookup_public_structure()
    assert allowed_tools(s)=={'hold_candidate'}
    assert '거부' in t.predict_structure('예측')


def replace_candidate(c):
    c=copy.deepcopy(c);c['candidate_id']='second';return c


def test_contact_calculation_excludes_outside_input_residues(tmp_path):
    p=tmp_path/'synthetic.cif';p.write_text(cif())
    mapping=[{'role':role,'label_asym_id':chain} for role,chain in [('target','T'),('heavy','H'),('light','L')]]
    measured=analysis.predicted_contact_measurement(p,mapping,{},predicted=False,
        residue_ranges={'T':(2,3),'H':(1,4),'L':(1,4)})
    assert measured.state=='measured'
    assert all(r['label_seq_id'] in {2,3} for r in measured.residues if r['label_asym_id']=='T')


def test_alternate_coordinates_are_reusable_but_not_measurement_proof(monkeypatch,tmp_path):
    monkeypatch.setattr(sources,'download',lambda pdb:cif().replace('0 1 1 . author-T','0 1 0.5 A author-T').encode())
    result=sources.lookup(input_candidate(),'ACD',tmp_path)
    assert result.complete and '대체 좌표' in result.calculation_hold_reason


@pytest.mark.parametrize('status, chunks, message',[(302,[b'data_'],'HTTP 302'),(200,[b'12345'],'크기 제한')])
def test_download_uses_fixed_endpoint_and_bounds_response(monkeypatch,status,chunks,message):
    # This test exercises the actual transport wrapper, not the autouse fixture.
    class Response:
        status_code=status
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,size):return iter(chunks)
    calls=[]
    def get(url,**kwargs):calls.append((url,kwargs));return Response()
    monkeypatch.setattr(sources.requests,'get',get)
    monkeypatch.setattr(sources,'MAX_BYTES',4)
    with pytest.raises(ValueError,match=message):DOWNLOAD('1ABC')
    assert calls==[('https://files.rcsb.org/download/1ABC.cif',{'timeout':(5,20),'stream':True,'allow_redirects':False})]


class SearchResponse:
    def __init__(self,body,status=200):
        import json
        self.status_code=status
        self.content=b'' if body is None else json.dumps(body).encode()
        self.body=body
    def json(self):return self.body


def enable_search(monkeypatch,body,status=200):
    monkeypatch.setenv('PDB_SEARCH_ENABLED','1')
    calls=[]
    def post(url,**kwargs):calls.append((url,kwargs));return SearchResponse(body,status)
    monkeypatch.setattr(sources.requests,'post',post)
    return calls


def long_cif():
    target=sources.structures.her2_target_sequence()
    return cif([('T',target),('H','FGHI'*15),('L','KLMN'*15)])


def test_automatic_search_validates_full_chains_not_just_api_similarity(monkeypatch,tmp_path):
    calls=enable_search(monkeypatch,{'total_count':1,'result_set':[{'identifier':'1ABC','score':1.0}]})
    monkeypatch.setattr(sources,'download',lambda pdb:long_cif().encode())
    c=candidate('auto','Any name','FGHI'*15,'KLMN'*15)
    result=sources.lookup(c,sources.structures.her2_target_sequence(),tmp_path)
    assert result.complete and result.pdb_id=='1ABC' and len(calls)==1
    assert calls[0][1]['json']['query']['parameters']['identity_cutoff']==1.0
    c['light_chain_fasta']='KLMN'*14+'ALMN'
    result=sources.lookup(c,sources.structures.her2_target_sequence(),tmp_path)
    assert not result.complete and not result.blocked_reason


def test_no_search_hit_keeps_prediction_available_without_claiming_global_absence(monkeypatch,tmp_path):
    enable_search(monkeypatch,None,204)
    result=sources.lookup(candidate('auto','any','FGHI'*15,'KLMN'*15),sources.structures.her2_target_sequence(),tmp_path)
    assert not result.complete and not result.blocked_reason
    assert '제한된 자동 검색' in result.notes[0]


def test_known_exact_local_structure_needs_no_automatic_search(monkeypatch,tmp_path):
    monkeypatch.setenv('PDB_SEARCH_ENABLED','1')
    def forbidden(*args,**kwargs):raise AssertionError('must not search')
    monkeypatch.setattr(sources.requests,'post',forbidden)
    public=sources.structures.load_catalog()['1N8Z']
    c=candidate('known','renamed',public.by_role('heavy')[0].sequence,public.by_role('light')[0].sequence)
    assert sources.lookup(c,sources.structures.her2_target_sequence(),tmp_path).complete


@pytest.mark.parametrize('body,status',[
    ({'total_count':8,'result_set':[{'identifier':'1ABC'}]},200),
    ({'total_count':1,'result_set':[]},200),
    ({'total_count':1,'result_set':[{'identifier':'../bad'}]},200),
    ({'total_count':1,'result_set':[{'identifier':[]}]},200),
    ([],200),
    (None,503),
    (None,302),
])
def test_incomplete_or_failed_search_holds_instead_of_predicting(monkeypatch,tmp_path,body,status):
    enable_search(monkeypatch,body,status)
    result=sources.lookup(candidate('auto','any','FGHI'*15,'KLMN'*15),sources.structures.her2_target_sequence(),tmp_path)
    assert result.blocked_reason and not result.complete


def test_unrelated_target_search_hit_is_rejected_without_hiding_other_hit(monkeypatch,tmp_path):
    enable_search(monkeypatch,{'total_count':2,'result_set':[{'identifier':'1ABC'},{'identifier':'2ABC'}]})
    def download(pdb):
        text=long_cif() if pdb=='1ABC' else cif([('T','ACD'),('H','FGHI'*15),('L','KLMN'*15)],pdb='2ABC')
        return text.encode()
    monkeypatch.setattr(sources,'download',download)
    result=sources.lookup(candidate('auto','any','FGHI'*15,'KLMN'*15),sources.structures.her2_target_sequence(),tmp_path)
    assert result.complete and result.pdb_id=='1ABC'
    assert any('2ABC' in note and '일치하지' in note for note in result.notes)
