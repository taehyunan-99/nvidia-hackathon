import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {parseScenarioFile} from '../src/scenario-file.ts';
const fixture=JSON.parse(await readFile(new URL('../../docs/frontend-hosting/fixtures/scenarios.json',import.meta.url),'utf8'));
test('saved data preserves mode boundaries and does not call malformed live data a mock upload',()=>{
 const data={...structuredClone(fixture),scenarios:[structuredClone(fixture.scenarios.find(s=>s.name==='completed'))]};
 data.data_mode='live';data.scenarios[0].session.data_mode='live';data.scenarios[0].run.data_mode='live';data.scenarios[0].result.data_mode='live';
 assert.equal(parseScenarioFile(data),data);
 data.scenarios[0].result.data_mode='mock';
 assert.throws(()=>parseScenarioFile(data),error=>error.message.includes('검토 데이터')&&!error.message.includes('모의'));
});
