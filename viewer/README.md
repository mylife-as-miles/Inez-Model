# Inez playable character viewer

Local Three.js 0.180 / Vite 7 viewer for the authored Inez GLB. The page uses `../assets` as its public directory. It loads `/characters/inez/model/inez.glb` only when `/characters/inez/qa/production_status.json` truthfully sets `model_available` to true. Production approval remains a separate status. There is no substitute character or generated animation fallback.

```bash
cd /workspace/viewer
npm ci
npm run dev
```

Open `http://localhost:4173/`. `npm run build` produces a local distribution; `npm run preview` serves it on port 4174. This work does not publish or deploy a website.

## Play and inspection

Click the canvas, then use WASD or arrow keys to move relative to the camera and Shift to run. Automatic locomotion smooths velocity/yaw, blends the actual Idle/Walk/Run clips continuously, and synchronizes Walk/Run phase. Its speed slider previews gait in place. Actual matching speeds come from `rig/animation_manifest.json` when present, otherwise rates are explicitly provisional. The manual clip menu blends actual AnimationMixer actions with adjustable transition duration; interrupted transitions retain current weights. Playback rate, pause, scrub and exported rest pose are available. Controls require actual matching assets and stay disabled when unavailable.

Facial controls bind only the named functional expression, viseme and blink targets, on every mesh containing them. Unclassified targets, including `Inez_HeadFit_*`, retain their exported influence. Neutral/reset never zero the entire morph array. Head/eye/jaw overlays restore their previous unmodified quaternions before every Mixer update and apply once afterward. Gaze and jaw axes use the head's world rotation relative to its exported rest orientation, accounting for anatomical bone roll. Dotted bone names resolve after GLTFLoader sanitization.

Orbit/zoom and body/face front, left, right, three-quarter and back views are orthographic. Studio and apartment lighting have exposure/key/fill/ambient sliders. Material views include PBR, albedo, actual roughness-map green channel multiplied by its factor, normal texture and geometry normals; a material can be selected and wireframe enabled. Inspection retains glTF base-color alpha coverage in the WebGL2 backend. Roughness inspection does not display the red AO or blue metallic channels as roughness. Reference comparison retains the originals as final authority. Stats report measured FPS, actual renderer draw/triangle/resource counts and GLB byte size.

The default backend is WebGL2. `?renderer=webgpu` requests the optional Three.js WebGPU backend with WebGL2 fallback. WebGPU hardware/material compatibility has not been validated.

## Browser QA API

`window.inezViewer` exposes:

- `state`, `errors`, `warnings`, `assetInfo` (also `state.assetInfo`). State includes `ready`, `loading`, `productionStatus`, `backend`, `animationMode`, `currentAnimation`, `actionWeights`, `clipTime`, `clipDuration`, `playbackRate`, `locomotionSpeed`, `previewSpeed`, `characterPosition`, `characterYaw`, `velocity` and `facialControls`.
- `setView(name)` with `body_front`, `body_left`, `body_right`, `body_three_quarter`, `body_back`, and equivalent `face_*` names. `setLighting('studio'|'apartment', {exposure,key,fill,ambient})`; `setLightControls(values)` adjusts current values.
- `setAnimation('Idle'|'Walk'|'Run'|'automatic'|'rest', {transition:0, restart:true})`. Actual extra clips can also be selected by name. Missing clip requests return false. `setPlaybackSpeed(rate)`.
- `setLocomotionSpeed(metersPerSecond, {immediate:true, move:false, direction:[0,0,1]})`. Default preview is in place. `move:true` explicitly enables scripted translation. Keyboard translation remains camera relative.
- `setExpression(name, strength=1)`, `setViseme('AA'|'EE'|'OH'|'MM'|'FV'|'none', strength=1)` (full exported names and case-insensitive `Neutral`/`rest` aliases also work), `setFaceControls({blinkLeft,blinkRight,autoBlink,jaw,eyeYaw,eyePitch,headYaw,headPitch,headRoll})`, `resetFace()`. Angular controls use degrees; strength/blink/jaw use 0–1.
- `pause(true)`, `seek(seconds)` for active clip/normalized gait phase, `advance(seconds)` for deterministic real Mixer/locomotion steps, `resetPosition()`. `advance` works while paused, is limited to ten seconds per call and uses steps no larger than 1/60 s. `seek` itself does not pause; use `pause` first for repeatable captures.
- `captureMode(true,{freeze:true})` hides the page UI, freezes playback, disables automatic blink/orbit and restores those settings when switched off. `renderFrame()` refreshes the current real pose.
- `getAvatar()` / read-only `avatar`, `getBone(name)`, `boneWorldPositions([names])` (alias `getBoneWorldPositions`) returning `{requestedName:{name,position:[x,y,z],quaternion:[x,y,z,w]}}`.
- `sampleDeformedVertices(meshName,[indices])` returning `{mesh,skinned,vertexCount,samples:[{index,local:[x,y,z],world:[x,y,z]}]}`. It evaluates the actual morph/skinning pipeline. Read-only `meshInventory` / `assetInfo.meshInventory` supplies mesh names, vertex counts, skin flags and morph names.
- `getMorphInfluences()` returning `[{mesh,targets:[{name,index,value,initial,controlled}]}]` so fit preservation is independently inspectable. `assetInfo.preservedMorphs` records initial values.
- `inspectMaterials(mode, materialUuid='all')`, `setWireframe(true)`, `setReference(relativeReferencePath|'none')`. Read-only `effectiveWeights` and `actorPosition` are convenient state aliases.

For a fixed frame, pause, select a real clip with transition zero, seek, select camera/lighting, then enter capture mode. Samples and frame advancement are invalid without an authored model and return false/null/empty data as appropriate.

## Verification scope

`npm run build` passed. `python qa/unavailable-preflight.py` regenerates the Chromium/SwiftShader report in `qa/unavailable_preflight.json` for the unavailable-asset viewer foundation: no GLB requested, no fake model, disabled asset controls, all view presets, lighting sliders, original reference image loading and capture mode, with no page or console errors. Detached synthetic material fixtures additionally verify alpha coverage and the roughness green channel. The two preflight screenshots show the unavailable viewer only.

`node --test qa/character-controls.test.mjs` passes six synthetic module regressions for interrupted blends, action reuse, fade timing, automatic-to-manual transition, fit preservation and facial overlay restoration, and resting-mouth aliases. These fixtures never appear as a character in the viewer and do not certify the actual GLB.

The authored model, clip deformation/loops, facial targets, default-fit preservation under real animation, keyboard movement/blending, PBR maps, and hardware performance require the actual final GLB and separate browser QA. Source preparation passing does not certify those model-dependent results or likeness.
