import test from 'node:test';
import assert from 'node:assert/strict';
import { buildCues, cuesIn } from '../js/player/mixplan.js';

const P = { clips: [
  { id: 'vo', track: 'voice', kind: 'audio', src: 'v.mp3', start: 0, in: 1, dur: 2 },
  { id: 'pz', track: 'voice', kind: 'pause', start: 2, dur: 1 },
  { id: 's', track: 'sfx1', src: 's.wav', start: 0.5, dur: 0.4, volume_db: -9 },
  { id: 'm', track: 'music', src: 'm.wav', start: 0, dur: 10, loop: true, fade_in: 0.5, fade_out: 0.8, volume_db: -17 },
  { id: 'v', track: 'v1', kind: 'video', src: 'x.mp4', start: 3, dur: 2, in: 4, volume_db: -22 },
  { id: 'vm', track: 'v1', kind: 'video', src: 'y.mp4', start: 5, dur: 2, mute: true },
] };
test('cues by bus, pause skipped, muted video skipped', () => {
  const c = buildCues(P);
  assert.deepEqual(c.map((x) => [x.id, x.bus]), [['vo', 'voice'], ['m', 'music'], ['s', 'sfx'], ['v', 'video']]);
  assert.equal(c[0].offset, 1); assert.equal(c[1].loop, true); assert.equal(c[3].element, true);
});
test('off and solo', () => {
  assert.equal(buildCues(P, { off: { music: true } }).find((x) => x.bus === 'music'), undefined);
  assert.deepEqual(buildCues(P, { solo: 'sfx1' }).map((x) => x.id), ['s']);
});
test('cuesIn window', () => { assert.deepEqual(cuesIn(buildCues(P), 2.1, 2.9).map((x) => x.id), ['m']); });
