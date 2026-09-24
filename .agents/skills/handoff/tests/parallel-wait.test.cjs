const test = require('node:test');
const assert = require('node:assert/strict');
const { reduceWait, waitForBatch } = require('../scripts/parallel_wait.js');

function checkpoint(count = 5) {
  return { id: 'batch-1', mode: 'tools', review_on: 'batch', deadline_ms: 100000,
    targets: Array.from({length: count}, (_, i) => ({task_id: 'T'+i, thread_id: 'app-'+i, host_id: 'local', turn_id: 'exec-'+i})),
    cursors: {}, completed: [], calls: 0, status: 'waiting', reason: null };
}
function poll(i, status = 'completed', extra = {}) {
  return {thread: {id: 'app-'+i, hostId: 'local', status: {type: 'idle'}}, cursor: 'opaque-'+i,
    latestTurn: {id: 'exec-'+i, status}, ...extra};
}
const result = (...polls) => ({timedOut: false, wake: {reason: 'turnCompleted'}, polls});

test('five ordinary completions produce one batch return, retaining five app calls', async () => {
  const events = Array.from({length: 5}, (_, i) => result(poll(i)));
  let calls = 0, saves = 0;
  const final = await waitForBatch(checkpoint(), {
    now: () => 0, wait: async () => events[calls++], save: async value => {saves++; return value;}
  });
  assert.equal(final.status, 'ready');
  assert.equal(final.completed.length, 5);
  assert.equal(calls, 5);
  assert.equal(saves, 5);
  console.log('Replay: 5 completion events, 5 app tool calls, 1 model-visible batch return (per-event baseline: 5).');
});

test('progress and duplicate completion preserve cursors without an early return', async () => {
  const events = [result(poll(0, 'inProgress')), result(poll(1)), result(poll(1)), result(poll(0))];
  const seen = [];
  const final = await waitForBatch(checkpoint(2), {now: () => 0,
    wait: async args => {seen.push(args); return events.shift();}, save: async x => x});
  assert.equal(final.status, 'ready');
  assert.equal(final.completed.length, 2);
  assert.equal(seen[1].targets.find(t => t.threadId === 'app-0').afterCursor, 'opaque-0');
  assert.equal(seen[2].targets.length, 1);
});

test('completion before the first wait is recovered from the snapshot', async () => {
  let calls = 0;
  const final = await waitForBatch(checkpoint(2), {now: () => 0,
    wait: async () => {calls++; return result(poll(0), poll(1));}, save: async x => x});
  assert.equal(final.status, 'ready');
  assert.equal(calls, 1);
});

test('failure, approval, user interruption and connection errors return promptly', () => {
  for (const event of [result(poll(0, 'failed')),
    result(poll(0, 'inProgress', {thread: {id:'app-0',hostId:'local',status:{activeFlags:['waitingOnApproval']}}})),
    {wake:{reason:'actionableStatus',threadId:'app-0'},polls:[poll(0,'inProgress')]},
    {wake:{reason:'userInput'},polls:[]}, {errors:[{threadId:'app-0',error:'disconnected'}]}]) {
    assert.equal(reduceWait(checkpoint(), event).status, 'attention');
  }
});

test('a reporting follow-up cannot stand in for the original execution turn', () => {
  const final = reduceWait(checkpoint(), result(poll(0, 'completed', {latestTurn:{id:'report-turn',status:'completed'}})));
  assert.equal(final.status, 'attention');
  assert.equal(final.completed.length, 0);
});

test('foreign task observations do not complete a role', () => {
  const final = reduceWait(checkpoint(), result(poll(99)));
  assert.equal(final.completed.length, 0);
});

test('more than eight targets are rotated through bounded app calls', async () => {
  const sizes = [];
  const final = await waitForBatch(checkpoint(12), {now: () => 0,
    wait: async args => {sizes.push(args.targets.length); return result(...args.targets.map(t => poll(Number(t.threadId.slice(4)))));},
    save: async x => x});
  assert.equal(final.status, 'ready');
  assert.deepEqual(sizes, [8,4]);
});

test('deadline and checkpoint-save failure cannot spin or claim readiness', async () => {
  const timed = await waitForBatch(checkpoint(), {now: () => 100000, wait: () => assert.fail(), save: async x => x});
  assert.equal(timed.status, 'attention');
  const failed = await waitForBatch(checkpoint(), {now: () => 0, wait: async () => result(poll(0)), save: async () => {throw Error('stale revision');}});
  assert.equal(failed.status, 'attention');
});

test('explicit early review returns once; manual wait and delivered checkpoints do not call app tools', async () => {
  const early = await waitForBatch({...checkpoint(),review_on:'first'}, {now: () => 0, wait: async () => result(poll(0)), save: async x => x});
  assert.equal(early.status, 'ready');
  assert.equal(early.completed.length, 1);
  for (const value of [{...checkpoint(),mode:'user'}, {...checkpoint(),status:'ready'}]) {
    const answer = await waitForBatch(value, {wait: () => assert.fail(), save: () => assert.fail()});
    assert.ok(['waiting_user','inspect_checkpoint'].includes(answer.status));
  }
});
