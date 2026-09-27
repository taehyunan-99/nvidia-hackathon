import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

const fixture=JSON.parse(await readFile(new URL('../../docs/frontend-hosting/fixtures/scenarios.json',import.meta.url),'utf8'));
test('report distinguishes missing calculations from measured values and model confidence',async()=>{
 const vite=await createServer({root:new URL('..',import.meta.url).pathname,server:{middlewareMode:true},appType:'custom'});
 try {
  const {ReportView}=await vite.ssrLoadModule('/src/ReportView.tsx');
  const original=fixture.scenarios.find(s=>s.name==='completed');
  for(const state of ['unknown','not_run','failed','measured']) {
   const frame=structuredClone(original);
   const evidence=frame.result.evidence[0];
   Object.assign(evidence,{kind:'computed',measurement_state:state,structure_id:'st-test',value:state==='measured'?0:null,topic:'surface_exposure'});
   frame.result.evidence=[evidence];
   frame.result.opinions=[{...frame.result.opinions[0],evidence_ids:[evidence.evidence_id],conflicting_evidence_ids:[]}];
   const html=renderToStaticMarkup(createElement(ReportView,{result:frame.result,input:fixture.input,run:frame.run,persistedMock:true,apiBase:''}));
   if(state==='measured') assert.match(html,/구조에서 계산한 값/);
   else {assert.doesNotMatch(html,/구조에서 계산한 값/);assert.match(html,/계산값 없음/);}
  }
  const frame=structuredClone(original);
  const e=frame.result.evidence[0];
  Object.assign(e,{kind:'computed',measurement_state:'measured',structure_id:'st-test',value:0.8,topic:'prediction_confidence'});
  frame.result.evidence=[e];frame.result.opinions=[{...frame.result.opinions[0],evidence_ids:[e.evidence_id],conflicting_evidence_ids:[]}];
  const html=renderToStaticMarkup(createElement(ReportView,{result:frame.result,input:fixture.input,run:frame.run,persistedMock:true,apiBase:''}));
  assert.match(html,/모델이 제공한 신뢰도/);
 } finally {await vite.close();}
});
