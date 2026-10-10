// Skin diffusion profiles as sums of Gaussians (d'Eon & Luebke, GPU Gems 3
// ch. 14). R(r) = sum_i w_i * G(v_i, r), G(v, r) = exp(-r^2 / (2v)) / (2*pi*v),
// with variances v in mm^2 shared by the three colour channels and RGB
// weights per Gaussian; each channel's weights sum to 1, so the albedo
// texture alone sets the skin colour (the chapter's normalisation).
//
// The six-Gaussian skin fit is printed in the chapter's Figure 14-13 (the
// text describes it but does not list the numbers). The values below are
// that published fit; their per-channel sums are exactly 1.000, as the text
// requires, which the unit test checks.

export interface Gaussian { variance: number; weights: [number, number, number] }
export interface DiffusionProfile { name: string; gaussians: Gaussian[]; source: string }

export const SKIN_SIX: DiffusionProfile = {
  name: 'skin-6 (three-layer skin, sum of six Gaussians)',
  source: "d'Eon & Luebke, GPU Gems 3 ch. 14, Fig. 14-13",
  gaussians: [
    { variance: 0.0064, weights: [0.233, 0.455, 0.649] },
    { variance: 0.0484, weights: [0.100, 0.336, 0.344] },
    { variance: 0.187, weights: [0.118, 0.198, 0.0] },
    { variance: 0.567, weights: [0.113, 0.007, 0.007] },
    { variance: 1.99, weights: [0.358, 0.004, 0.0] },
    { variance: 7.41, weights: [0.078, 0.0, 0.0] },
  ],
};

/**
 * Reduce a profile to fewer Gaussians for cheaper presets: adjacent
 * Gaussians are merged into one with the weight-averaged variance, keeping
 * every channel's total weight (so colour is preserved).
 */
export function reduceProfile(profile: DiffusionProfile, groups: number[][], name: string): DiffusionProfile {
  const gaussians = groups.map(group => {
    const weights: [number, number, number] = [0, 0, 0];
    let mass = 0, varianceSum = 0;
    for (const index of group) {
      const g = profile.gaussians[index];
      g.weights.forEach((w, c) => { weights[c] += w; });
      const m = (g.weights[0] + g.weights[1] + g.weights[2]) / 3;
      mass += m; varianceSum += m * g.variance;
    }
    return { variance: mass > 0 ? varianceSum / mass : profile.gaussians[group[0]].variance, weights };
  });
  return { name, gaussians, source: `${profile.source}, reduced to ${groups.length} Gaussians` };
}

export const SKIN_FOUR = reduceProfile(SKIN_SIX, [[0], [1], [2, 3], [4, 5]], 'skin-4 (gameplay)');
export const SKIN_THREE = reduceProfile(SKIN_SIX, [[0, 1], [2, 3], [4, 5]], 'skin-3 (VR)');

/** Radial profile value per channel at distance r (mm). */
export function evaluate(profile: DiffusionProfile, r: number): [number, number, number] {
  const out: [number, number, number] = [0, 0, 0];
  for (const g of profile.gaussians) {
    const value = Math.exp(-r * r / (2 * g.variance)) / (2 * Math.PI * g.variance);
    g.weights.forEach((w, c) => { out[c] += w * value; });
  }
  return out;
}

export function channelSums(profile: DiffusionProfile): [number, number, number] {
  return profile.gaussians.reduce<[number, number, number]>((s, g) => [s[0] + g.weights[0], s[1] + g.weights[1], s[2] + g.weights[2]], [0, 0, 0]);
}

/** The chapter's 7-tap separable Gaussian kernel weights; the tap spacing is scaled by each Gaussian's standard deviation (and by the UV stretch). */
export const SEVEN_TAP = [0.006, 0.061, 0.242, 0.383, 0.242, 0.061, 0.006];
