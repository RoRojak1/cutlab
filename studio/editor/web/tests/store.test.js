import test from 'node:test';
import assert from 'node:assert/strict';
import { Store } from '../js/store.js';

function fakeApi() {
  const calls = [];
  let rev = 1;
  const proj = () => ({ revision: rev, clips: [{ id: 'A', track: 'v1', start: 0, dur: 2 }, { id: 'B', track: 'v1', start: 2, dur: 2 }], tracks: [{ id: 'v1' }], title: 't' });
  return {
    calls,
    async get(u) {
      if (u.endsWith('/words')) return { words: [[0.1, 'p:0', 'one']] };
      if (u.endsWith('/review')) return { comments: [], notifications: [], batches: [], jobs: [], presence: 'offline' };
      if (u.includes('/library/')) return { sounds: [], music: [] };
      return proj();
    },
    async post(u, b) { calls.push([u, b]); rev += 1; return { revision: rev, inverse: [{ op: 'inv', of: b.ops[0].op }], changed: ['A'], rebased: false, project: proj() }; },
  };
}

test('dispatch → undo → redo', async () => {
  const api = fakeApi();
  const s = new Store(api, 'tst');
  await s.load();
  await s.dispatch([{ op: 'set', id: 'A', fields: { motion: 'shake' } }], { label: 'движение' });
  assert.equal(s.project.revision, 2);
  assert.ok(s.canUndo());
  await s.undoLast();
  assert.deepEqual(api.calls[1][1].ops, [{ op: 'inv', of: 'set' }]);
  assert.ok(s.canRedo());
  await s.redoLast();
  // redo must resend the server-provided inverse-of-the-undo (id-stable), not the original ops —
  // here the fake server's generic inverse wrapper of call[1]'s op ({op:'inv',of:'set'}) is {op:'inv',of:'inv'}.
  assert.deepEqual(api.calls[2][1].ops, [{ op: 'inv', of: 'inv' }]);
  assert.equal(s.canRedo(), false);
});

test('clipAt and select', async () => {
  const s = new Store(fakeApi(), 'tst');
  await s.load();
  assert.equal(s.clipAt('v1', 2.5).id, 'B');
  let got = null; s.on('sel', (v) => { got = [...v]; });
  s.select(['A']); s.select(['B'], 'toggle');
  assert.deepEqual(got, ['A', 'B']);
});

test('external event refetches and emits', async () => {
  const s = new Store(fakeApi(), 'tst');
  await s.load();
  let ext = null; s.on('external', (e) => { ext = e; });
  await s.onServerEvent({ type: 'project', revision: 5, changed: ['B'], by: 'claude' });
  assert.deepEqual(ext.changed, ['B']);
});

// Fake server with minimal split/add/remove/set semantics: 'split' mints a fresh id each time
// it is dispatched (like the real server would), while 'remove'/'add' are id-stable — they
// operate on the exact id passed in the op, the way a server-computed inverse would.
function fakeApiIds() {
  const calls = [];
  let rev = 1;
  let counter = 0;
  let clips = [{ id: 'A', track: 'v1', start: 0, dur: 4 }];
  const proj = () => ({ revision: rev, clips: clips.map((c) => ({ ...c })), tracks: [{ id: 'v1' }], title: 't' });
  function apply(op) {
    if (op.op === 'split') {
      const c = clips.find((x) => x.id === op.id);
      const newId = 'S' + (++counter);
      const origDur = c.dur;
      c.dur = op.at;
      clips.push({ id: newId, track: c.track, start: c.start + op.at, dur: origDur - op.at });
      return { op: 'remove', id: newId, restoreId: op.id, restoreDur: origDur };
    }
    if (op.op === 'remove') {
      const idx = clips.findIndex((x) => x.id === op.id);
      const removedSnapshot = { ...clips[idx] };
      const ownerCurrentDur = clips.find((x) => x.id === op.restoreId).dur;
      clips = clips.filter((x) => x.id !== op.id);
      clips.find((x) => x.id === op.restoreId).dur = op.restoreDur;
      return { op: 'add', clip: removedSnapshot, shrinkId: op.restoreId, shrinkDur: ownerCurrentDur };
    }
    if (op.op === 'add') {
      clips.push({ ...op.clip });
      const owner = clips.find((x) => x.id === op.shrinkId);
      const ownerDurBefore = owner.dur;
      owner.dur = op.shrinkDur;
      return { op: 'remove', id: op.clip.id, restoreId: op.shrinkId, restoreDur: ownerDurBefore };
    }
    if (op.op === 'set') {
      const c = clips.find((x) => x.id === op.id);
      const prev = {}; for (const k in op.fields) prev[k] = c[k];
      Object.assign(c, op.fields);
      return { op: 'set', id: op.id, fields: prev };
    }
    throw new Error('unknown op ' + op.op);
  }
  return {
    calls,
    async get(u) {
      if (u.endsWith('/words')) return { words: [] };
      if (u.endsWith('/review')) return { comments: [], notifications: [], batches: [], jobs: [], presence: 'offline' };
      if (u.includes('/library/')) return { sounds: [], music: [] };
      return proj();
    },
    async post(u, b) {
      calls.push([u, b]);
      const inv = apply(b.ops[0]);
      rev += 1;
      return { revision: rev, inverse: [inv], changed: [], rebased: false, project: proj() };
    },
  };
}

test('undo/redo preserves ids across an id-generating op (split)', async () => {
  const api = fakeApiIds();
  const s = new Store(api, 'tst');
  await s.load();

  await s.dispatch([{ op: 'split', id: 'A', at: 2 }], { label: 'split' });
  const newId = s.project.clips.find((c) => c.id !== 'A').id;
  assert.equal(newId, 'S1');

  await s.dispatch([{ op: 'set', id: newId, fields: { motion: 'shake' } }], { label: 'motion' });
  assert.equal(s.clip(newId).motion, 'shake');

  await s.undoLast(); // undo the set
  assert.equal(s.clip(newId).motion, undefined);
  await s.undoLast(); // undo the split
  assert.equal(s.project.clips.length, 1);

  await s.redoLast(); // redo the split
  const redoneId = s.project.clips.find((c) => c.id !== 'A').id;
  assert.equal(redoneId, newId, 'redo must recreate the same id, not mint a new one');

  // the redo of the split must send the server-provided inverse-of-inverse (an id-stable 'add'), not the original 'split' op
  const lastOps = api.calls[api.calls.length - 1][1].ops;
  assert.equal(lastOps[0].op, 'add');
  assert.equal(lastOps[0].clip.id, newId);

  await s.redoLast(); // redo the set — must succeed against the SAME id
  assert.equal(s.clip(newId).motion, 'shake');
  assert.equal(s.canRedo(), false);
});

test('a slower in-flight dispatch does not overwrite a newer revision', async () => {
  let rev = 1;
  const api = {
    async get() { return { revision: rev, clips: [], tracks: [], title: 't' }; },
    async post(u, b) {
      rev += 1;
      const myRev = rev;
      if (b.ops[0].delay) await new Promise((res) => setTimeout(res, b.ops[0].delay));
      return { revision: myRev, inverse: [{ op: 'noop' }], changed: [], rebased: false, project: { revision: myRev, clips: [], tracks: [], title: 't' } };
    },
  };
  const s = new Store(api, 'tst');
  await s.load(); // revision 1

  const slow = s.dispatch([{ op: 'noop', delay: 30 }], { record: false }); // becomes revision 2, resolves late
  const fast = s.dispatch([{ op: 'noop', delay: 0 }], { record: false }); // becomes revision 3, resolves first
  await Promise.all([slow, fast]);
  assert.equal(s.project.revision, 3);
});

test('a failed redo dispatch keeps the entry on the redo stack', async () => {
  const api = fakeApi();
  const s = new Store(api, 'tst');
  await s.load();
  await s.dispatch([{ op: 'set', id: 'A', fields: { motion: 'shake' } }], { label: 'move' });
  await s.undoLast();
  assert.ok(s.canRedo());

  const realPost = api.post.bind(api);
  api.post = async () => { throw new Error('network fail'); };
  await assert.rejects(() => s.redoLast());
  assert.ok(s.canRedo(), 'redo entry must not be lost when the dispatch fails');
  api.post = realPost;

  await s.redoLast(); // now succeeds
  assert.equal(s.canRedo(), false);
});

test('rapid undo presses are sent strictly in order (no interleaving)', async () => {
  const order = [];
  let rev = 1, inflight = 0, maxInflight = 0;
  const api = {
    async get() { return { revision: rev, clips: [], tracks: [], title: 't' }; },
    async post(u, b) {
      inflight += 1; maxInflight = Math.max(maxInflight, inflight);
      order.push(b.ops[0].n);
      await new Promise((res) => setTimeout(res, b.ops[0].delay || 0));
      inflight -= 1; rev += 1;
      return { revision: rev, inverse: [{ op: 'inv', n: -b.ops[0].n }], changed: [], rebased: false, project: { revision: rev, clips: [], tracks: [], title: 't' } };
    },
  };
  const s = new Store(api, 'tst');
  await s.load();
  s.undo = [{ ops: [{ n: 1 }], inverse: [{ op: 'x', n: 10, delay: 5 }], label: '1' }, { ops: [{ n: 2 }], inverse: [{ op: 'x', n: 20, delay: 30 }], label: '2' }];
  await Promise.all([s.undoLast(), s.undoLast()]);       // ⌘Z ⌘Z: сначала отмена второй, потом первой, по одной
  assert.deepEqual(order, [20, 10]);
  assert.equal(maxInflight, 1);
  assert.equal(s.redo.length, 2);
});

test('restore clears undo/redo', async () => {
  const s = new Store(fakeApi(), 'tst');
  await s.load();
  await s.dispatch([{ op: 'set', id: 'A', fields: { motion: 'shake' } }]);
  assert.ok(s.canUndo());
  s.setProject({ ...s.project, revision: 99 }, [], 'restore');
  assert.equal(s.canUndo(), false);
});
