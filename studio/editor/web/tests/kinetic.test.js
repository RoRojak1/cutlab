import test from 'node:test';
import assert from 'node:assert/strict';
import { kineticTimes } from '../js/player/kinetic.js';

const CASES = [
  { ost: '40 MILLION', en: 'Forty million people live below the line.', dur: 3.2, spoken: [['forty', 0.12], ['million', 0.45], ['people', 0.9], ['live', 1.2]], expect: [['40', 0.3], ['MILLION', 0.45]] },
  { ost: 'HEAT WATER FOOD', en: 'Heat, water, and food.', dur: 2.5, spoken: [['heat', 0.1], ['water', 0.7], ['and', 1.1], ['food', 1.3]], expect: [['HEAT', 0.1], ['WATER', 0.7], ['FOOD', 1.3]] },
  { ost: '+1 m', en: 'Plus one meter of sea level.', dur: 2.0, spoken: null, expect: [['+1', 0.3], ['m', 0.52]] },
  { ost: 'HUNDREDS OF MILLIONS', en: 'Hundreds of millions of people.', dur: 3.0, spoken: [['hundreds', 0.2], ['of', 0.7], ['millions', 0.8], ['of', 1.3], ['people', 1.4]], expect: [['HUNDREDS', 0.2], ['OF', 0.7], ['MILLIONS', 0.8]] },
];
for (const c of CASES) test(`kinetic ${c.ost}`, () => {
  const got = kineticTimes(c.ost, c.en, c.dur, c.spoken).map((x) => [x.w, Math.round(x.t * 1e4) / 1e4]);
  assert.deepEqual(got, c.expect);
});
