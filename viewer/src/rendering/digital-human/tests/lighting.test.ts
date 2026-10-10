// Black-body colours used by the lighting presets (no GPU).
import assert from 'node:assert/strict';
import test from 'node:test';
import { kelvinToLinear, PRESETS } from '../lighting/presets.ts';

test('6500 K is close to neutral, 2700 K is warm, all have unit luminance', () => {
  const d65 = kelvinToLinear(6500);
  assert.ok(Math.abs(d65.r - d65.b) < 0.12, `6500 K r=${d65.r} b=${d65.b}`);
  const warm = kelvinToLinear(2700);
  assert.ok(warm.r > warm.g && warm.g > warm.b);
  for (const c of [d65, warm, kelvinToLinear(4000)]) assert.ok(Math.abs(0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b - 1) < 1e-6);
});

test('the six evaluation environments exist', () => {
  assert.deepEqual(Object.keys(PRESETS).sort(), ['apartment', 'backlight', 'daylight', 'flashlight', 'practical', 'studio']);
});
