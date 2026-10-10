// Diffusion-profile data checks (no GPU).
import assert from 'node:assert/strict';
import test from 'node:test';
import { channelSums, evaluate, SEVEN_TAP, SKIN_FOUR, SKIN_SIX, SKIN_THREE } from '../skin/profiles.ts';

test('every profile keeps unit weight per colour channel', () => {
  for (const profile of [SKIN_SIX, SKIN_FOUR, SKIN_THREE]) {
    for (const sum of channelSums(profile)) assert.ok(Math.abs(sum - 1) < 1e-9, `${profile.name}: ${sum}`);
  }
});

test('red scatters furthest, blue least (skin)', () => {
  for (const r of [1, 2, 3]) {
    const [red, green, blue] = evaluate(SKIN_SIX, r);
    assert.ok(red > green && green > blue, `r=${r} mm: ${red} ${green} ${blue}`);
  }
});

test('reduced profiles stay close to the six-Gaussian profile beyond 0.5 mm', () => {
  for (const reduced of [SKIN_FOUR, SKIN_THREE]) {
    for (const r of [0.5, 1, 2, 4]) {
      const a = evaluate(SKIN_SIX, r)[0], b = evaluate(reduced, r)[0];
      assert.ok(Math.abs(a - b) / a < 0.6, `${reduced.name} r=${r}: ${a} vs ${b}`);
    }
  }
});

test('the seven-tap kernel is normalised', () => {
  assert.ok(Math.abs(SEVEN_TAP.reduce((a, b) => a + b, 0) - 1) < 0.002);
});
