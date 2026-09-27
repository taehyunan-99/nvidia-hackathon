import test from 'node:test';
import assert from 'node:assert/strict';
import { runFromSearch, runUrl } from '../src/run-location.ts';
test('explicit run URLs preserve the requested run and reject ambiguous or invalid IDs', () => {
  assert.equal(runFromSearch('?run=run-abc').runId, 'run-abc');
  for (const search of ['?run=', '?run=../secret', '?run=run-a&run=run-b']) {
    assert.equal(runFromSearch(search).runId, null);
    assert.ok(runFromSearch(search).error);
  }
  assert.equal(runFromSearch('').error, '');
});
test('run links preserve same-origin path and unrelated parameters', () => {
  const value = runUrl('http://localhost:8080/?theme=dark', 'run-ab');
  assert.equal(value, 'http://localhost:8080/?theme=dark&run=run-ab');
});
