// Custom glTF attributes baked by v06_thickness.py on the fitted surface.
// This is geometric through-surface thickness, not measured dermal layers.
export const THICKNESS_ATTRIBUTE = '_inez_thickness';
export const THIN_REGION_ATTRIBUTE = '_inez_thin_region';
export function thicknessInfo(mesh) {
  const a = mesh.geometry.getAttribute(THICKNESS_ATTRIBUTE);
  const mask = mesh.geometry.getAttribute(THIN_REGION_ATTRIBUTE);
  return { mesh: mesh.name, available: Boolean(a && mask), source: 'rest-pose inward ray to opposite surface',
    units: 'metres', animated: 'vertex-carried approximation; not recomputed during deformation' };
}
