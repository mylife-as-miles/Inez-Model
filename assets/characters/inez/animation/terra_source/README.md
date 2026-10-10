# TERRA artifacts (provenance)

Empty until a licensed TERRA run exists. For each TERRA-retargeted motion, copy here the three artifacts that `terra retarget` publishes: `<name>.npz` (MyoFullBody trajectory), `<name>_analysis.npz` and, for non-flat motions, `<name>_terrain.json`. Copy them unchanged, together with a note of the source motion, its licence and the TERRA commit.

They are inputs to `tools/inez/motion/terra_to_isk.py`; nothing here is loaded by the browser. See `docs/INEZ_ANIMATION_PIPELINE.md` section B and `docs/INEZ_TERRA_INTEGRATION.md`.
