// GPU Gems 3, chapter 14, figure 14-13. Variance is in mm²; channel
// weights each sum to one. This is a diffusion profile, not a red glow.
export const SKIN_PROFILE = Object.freeze([
  { variance: .0064, rgb: [.233, .455, .649] },
  { variance: .0484, rgb: [.100, .336, .344] },
  { variance: .1870, rgb: [.118, .198, .000] },
  { variance: .5670, rgb: [.113, .007, .007] },
  { variance: 1.9900, rgb: [.358, .004, .000] },
  { variance: 7.4100, rgb: [.078, .000, .000] }
]);

export const SKIN_DEFAULTS = Object.freeze({ mode: 'existing', sss: true, strength: .55,
  radius: 1, roughnessVariation: 1, microNormal: .15, thinTransmission: false,
  debug: 'off', quality: 'gameplay' });

export function sanitizeSkinSettings(current, values = {}) {
  const next = { ...current };
  const limits = { strength: [0, 1], radius: [.25, 3], roughnessVariation: [0, 1], microNormal: [0, 1] };
  for (const [key, [lo, hi]] of Object.entries(limits)) {
    if (key in values && Number.isFinite(Number(values[key]))) next[key] = Math.max(lo, Math.min(hi, Number(values[key])));
  }
  for (const key of ['sss', 'thinTransmission']) if (key in values) next[key] = Boolean(values[key]);
  if (['existing', 'enhanced'].includes(values.mode)) next.mode = values.mode;
  if (['off', 'diffuse', 'normals', 'thickness', 'scattered'].includes(values.debug)) next.debug = values.debug;
  if (['cinematic', 'gameplay', 'low-spec', 'vr'].includes(values.quality)) next.quality = values.quality;
  return next;
}
