import {test} from 'node:test';
import assert from 'node:assert/strict';
import {displayEvents, actorLabel, followUp} from '../src/activity-state.ts';
const event=(kind,actor,name,extra={},candidate='a')=>({candidate_id:candidate,step_id:name,updated_at:'2026-09-27T00:00:00Z',activity:{event_id:`${candidate}-${name}`,kind,actor,name,phase:'completed',...extra}});

test('preflight remains code, separate from agent choices',()=>{
 assert.equal(actorLabel(event('tool','code','check_input')),'자동 입력 검사');
 assert.equal(actorLabel(event('tool','agent','lookup_public_structure')),'에이전트');
});
test('legacy fallback stages are retained without reclassifying another candidate',()=>{
 const stage=event('stage','workflow','reporting');
 const source=[event('fallback','rule','continue_by_rule'),stage,event('stage','workflow','reporting',{},'b')];
 const result=displayEvents(source);
 assert.equal(result.length,2);
 assert.equal(result[1].activity.actor,'rule');
 assert.equal(stage.activity.actor,'workflow');
});
test('explicit rule stages need no fallback and ambiguous historical stages are not invented',()=>{
 assert.equal(displayEvents([event('stage','rule','input_mapping')]).length,1);
 assert.equal(displayEvents([event('stage','workflow','input_mapping')]).length,0);
});
test('available options and legacy tool records are not treated as selections',()=>{
 for(const metadata of [{available_tools:['predict_structure','use_experimental_structure']},{next_action:'predict_structure, use_experimental_structure'}]) {
  assert.equal(followUp([event('tool','agent','lookup_public_structure',metadata)],['predict_structure','use_experimental_structure']).label,'가능한 도구');
 }
});
test('current tool execution supersedes stale availability',()=>{
 const result=followUp([event('tool','agent','lookup_public_structure',{available_tools:['predict_structure']}),event('tool','agent','predict_structure',{phase:'running'})],['predict_structure']);
 assert.deepEqual(result,{label:'실행 중',actions:['predict_structure']});
});
test('fallback and rule stages supersede old model options',()=>{
 const old=event('tool','agent','lookup_public_structure',{available_tools:['predict_structure']});
 const fallback=event('fallback','rule','continue_by_rule');
 assert.equal(followUp([old,fallback],[]).label,'현재 처리');
 assert.deepEqual(followUp([old,fallback,event('stage','rule','structure_comparison')],[]),{label:'완료한 단계',actions:['structure_comparison']});
});
test('an empty available list represents termination rather than another model choice',()=>{
 assert.deepEqual(followUp([event('tool','agent','submit_opinion',{available_tools:[],next_action:'종료'})],[]),{label:'후속 안내',actions:['종료']});
});

test('skipped rule steps and failed tools do not imply completion or reuse stale options',()=>{
 assert.equal(followUp([event('stage','rule','reporting',{phase:'skipped'})],[]).label,'생략한 단계');
 assert.deepEqual(followUp([event('tool','agent','lookup_public_structure',{available_tools:['predict_structure']}),event('tool','agent','predict_structure',{phase:'failed'})],[]),{label:'후속 안내',actions:['실패 기록 확인']});
});
