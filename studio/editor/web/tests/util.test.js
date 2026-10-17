import test from 'node:test';
import assert from 'node:assert/strict';
import { frame, fmtTC, fmtShift, parseTC, dbGain, clamp } from '../js/util.js';

test('frame rounds to 1/30', () => { assert.equal(frame(10 / 30 + 0.004), 10 / 30); });
test('fmtTC', () => { assert.equal(fmtTC(388.4), '6:28.40'); assert.equal(fmtTC(0), '0:00.00'); assert.equal(fmtTC(-3), '0:00.00'); });
test('fmtShift', () => { assert.equal(fmtShift(-0.34), '−0,34 с · 10 кадр.'); assert.equal(fmtShift(0.1), '+0,10 с · 3 кадр.'); });
test('parseTC', () => { assert.equal(parseTC('6:28.4'), 388.4); assert.equal(parseTC('12.5'), 12.5); });
test('dbGain / clamp', () => { assert.ok(Math.abs(dbGain(-6) - 0.501) < 0.001); assert.equal(clamp(5, 0, 3), 3); });
