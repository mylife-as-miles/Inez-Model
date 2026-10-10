// Budgets to measure on hardware; no preset constitutes an FPS guarantee.
export const QUALITY_PRESETS = Object.freeze({
  cinematic: { directions: 8, diffusion: true, description: 'Full-resolution skin diffusion, 48 neighboring samples' },
  gameplay: { directions: 4, diffusion: true, description: 'Full-resolution skin diffusion, 24 neighboring samples' },
  'low-spec': { directions: 4, diffusion: false, description: 'Enhanced PBR surface only' },
  vr: { directions: 4, diffusion: false, description: 'PBR surface, no diffusion or camera blur' }
});
export const TARGET_LAPTOP = Object.freeze({ name: 'Dell Precision 5540', gpu: 'NVIDIA Quadro T1000',
  vramGB: 4, ramGB: 16, measuredHere: false, initialQuality: 'gameplay' });
