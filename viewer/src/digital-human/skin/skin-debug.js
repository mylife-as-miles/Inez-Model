export const SKIN_DEBUG_MODES = ['off', 'diffuse', 'scattered', 'normals', 'thickness'];
export const debugModeIndex = mode => Math.max(0, SKIN_DEBUG_MODES.indexOf(mode));
