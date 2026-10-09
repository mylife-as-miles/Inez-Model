import { defineConfig } from 'vite';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

// KTX2 textures in the runtime GLBs need the Basis Universal transcoder at a
// fixed URL (KTX2Loader.setTranscoderPath). Serve three's copy at /basis/ in
// development and emit it into the build, so no file is duplicated in-repo.
const basisDir = fileURLToPath(new URL('./node_modules/three/examples/jsm/libs/basis/', import.meta.url));
const basisFiles = ['basis_transcoder.js', 'basis_transcoder.wasm'];
const basisTranscoder = {
  name: 'inez-basis-transcoder',
  configureServer(server) {
    server.middlewares.use((req, res, next) => {
      const name = req.url?.startsWith('/basis/') && req.url.slice(7).split('?')[0];
      if (!name || !basisFiles.includes(name)) return next();
      res.setHeader('Content-Type', name.endsWith('.wasm') ? 'application/wasm' : 'text/javascript');
      res.end(readFileSync(basisDir + name));
    });
  },
  generateBundle() {
    for (const name of basisFiles) this.emitFile({ type: 'asset', fileName: 'basis/' + name, source: readFileSync(basisDir + name) });
  }
};

// The dev server serves ../assets directly. Builds do not copy it (several
// GB of sources and work files); tools/inez/package_playable.py adds only the
// runtime files a standalone viewer needs.
export default defineConfig({ publicDir: '../assets', plugins: [basisTranscoder],
  build: { copyPublicDir: false },
  server: { host: '0.0.0.0', port: 4173 }, preview: { port: 4174 } });
