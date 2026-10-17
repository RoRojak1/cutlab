import test from 'node:test';
import assert from 'node:assert/strict';
import { snapTime } from '../js/timeline/snap.js';

const words = [[2.12, 'p:2', 'forty'], [2.6, 'p:3', 'million'], [4.12, 'p:4', 'people']];

test('snaps to word minus lead', () => {
  const r = snapTime(2.03, { words, pps: 60 });
  assert.equal(r.kind, 'word'); assert.equal(r.ref, 'p:2'); assert.ok(Math.abs(r.t - 2.0) < 1e-9); assert.equal(r.label, 'forty');
});
test('respects pixel threshold', () => { assert.equal(snapTime(2.3, { words, pps: 60 }).kind, null); });
test('edges and playhead', () => {
  assert.equal(snapTime(3.01, { words, edges: [3.0], pps: 60 }).kind, 'edge');
  assert.equal(snapTime(3.51, { words, playhead: 3.5, pps: 60 }).kind, 'playhead');
});
test('disabled returns input', () => { assert.deepEqual(snapTime(2.03, { words, disabled: true }), { t: 2.03, kind: null }); });
