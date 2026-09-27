import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createServer} from 'vite';

const fixture=JSON.parse(await readFile(new URL('../../docs/frontend-hosting/fixtures/scenarios.json',import.meta.url),'utf8'));
async function setup(t,status='completed') {
 const vite=await createServer({root:new URL('..',import.meta.url).pathname,server:{middlewareMode:true},appType:'custom'});
 t.after(()=>vite.close());
 const api=await vite.ssrLoadModule('/src/persistent-mock.ts');
 const calls=[];
 const state={status,runId:'run-test',now:1_000_000,heartbeatError:null,resultError:null};
 t.mock.method(Date,'now',()=>state.now);
 t.mock.method(globalThis,'fetch',async(url)=>{
  const path=new URL(url).pathname;calls.push(path);
  const frame=structuredClone(fixture.scenarios.find(s=>s.name===state.status));
  frame.run.run_id=state.runId;
  if(frame.result) frame.result.run_id=state.runId;
  if(path==='/api/session/heartbeat') {
   if(state.heartbeatError) return Response.json(state.heartbeatError.body,{status:state.heartbeatError.status});
   if(state.sessionId) frame.session.session_id=state.sessionId;
   return Response.json(frame.session);
  }
  if(path===`/api/runs/${state.runId}`) return Response.json(frame.run);
  if(path===`/api/reviews/${frame.run.review_id}`) return Response.json(fixture.input);
  if(path===`/api/runs/${state.runId}/result`) {
   if(state.resultError) return Response.json({message:'temporary failure'},{status:503});
   return Response.json(frame.result);
  }
  throw new Error(`unexpected request: ${path}`);
 });
 return {api,state,calls,count:part=>calls.filter(p=>p.includes(part)).length};
}

test('polls progress, fetches immutable input once, then only renews the completed session',async t=>{
 const {api,state,count}=await setup(t,'queued');
 let previous=await api.readSavedRun(state.runId);
 assert.equal(api.isSavedRunFinished(previous),false);
 state.status='running';state.now+=2000;
 previous=await api.readSavedRun(state.runId,previous);
 assert.equal(previous.scenarios[0].run.status,'running');
 state.status='completed';state.now+=2000;
 previous=await api.readSavedRun(state.runId,previous);
 assert.equal(api.isSavedRunFinished(previous),true);
 assert.equal(count('/api/reviews/'),1);
 assert.equal(count(`/api/runs/${state.runId}`),4); // Three status requests and one result.
 for(let i=0;i<30;i++) {state.now+=2000;previous=await api.readSavedRun(state.runId,previous);}
 assert.equal(count(`/api/runs/${state.runId}`),4);
 assert.equal(count('/api/reviews/'),1);
 assert.equal(count('/heartbeat'),2);
});

for(const status of ['completed','partial','failed','interrupted']) {
 test(`${status} stops status/result downloads and preserves its result availability`,async t=>{
  const {api,state,count}=await setup(t,status);
  const previous=await api.readSavedRun(state.runId);
  const downloads=count('/api/runs/');
  state.now+=60_000;
  const current=await api.readSavedRun(state.runId,previous);
  assert.equal(api.isSavedRunFinished(current),true);
  assert.equal(count('/api/runs/'),downloads);
  assert.deepEqual(current.scenarios[0].result,previous.scenarios[0].result);
  assert.equal(count('/heartbeat'),2);
 });
}

for(const status of [401,404,410]) {
 test(`completed session still reports heartbeat ${status}`,async t=>{
  const {api,state}=await setup(t);
  const previous=await api.readSavedRun(state.runId);
  state.now+=60_000;state.heartbeatError={status,body:{code:status===410?'SESSION_EXPIRED':'SESSION_UNAVAILABLE',message:'session unavailable'}};
  await assert.rejects(api.readSavedRun(state.runId,previous),error=>error.status===status);
 });
}

test('retries a transient heartbeat failure without downloading the completed result again',async t=>{
 const {api,state,count}=await setup(t);
 const previous=await api.readSavedRun(state.runId);
 state.now+=60_000;state.heartbeatError={status:503,body:{message:'temporary failure'}};
 await assert.rejects(api.readSavedRun(state.runId,previous));
 state.heartbeatError=null;
 await api.readSavedRun(state.runId,previous);
 assert.equal(count('/result'),1);
 assert.equal(count('/heartbeat'),3);
});

test('a replaced browser session cannot keep displaying the previous session result',async t=>{
 const {api,state}=await setup(t);
 const previous=await api.readSavedRun(state.runId);
 state.now+=60_000;state.sessionId='different-session';
 await assert.rejects(api.readSavedRun(state.runId,previous),error=>error.status===401);
});

test('a failed result download can be retried before the run is cached as finished',async t=>{
 const {api,state,count}=await setup(t);
 state.resultError=true;
 await assert.rejects(api.readSavedRun(state.runId));
 state.resultError=false;
 const current=await api.readSavedRun(state.runId);
 assert.equal(api.isSavedRunFinished(current),true);
 assert.equal(count('/result'),2);
});

test('navigation to another run and a fresh page load fetch their own saved result',async t=>{
 const {api,state,calls}=await setup(t);
 const previous=await api.readSavedRun(state.runId);
 state.runId='run-other';
 const other=await api.readSavedRun(state.runId,previous);
 assert.equal(other.scenarios[0].result.run_id,'run-other');
 await api.readSavedRun(state.runId);
 assert.equal(calls.filter(p=>p==='/api/runs/run-other/result').length,2);
});
