// Structural validation of the actual binary asset using the Khronos validator.
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import validator from '../../viewer/node_modules/gltf-validator/index.js';
const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const source = process.argv[2] || path.join(repository, 'assets/characters/inez/model/inez.glb');
const target = process.argv[3] || path.join(repository, 'assets/characters/inez/qa/glb_validation.json');
const bytes = await fs.readFile(source);
const report = await validator.validateBytes(new Uint8Array(bytes), {
  uri: path.basename(source),
  maxIssues: 200,
  externalResourceFunction: async uri => { throw new Error(`GLB should embed resources; unresolved external URI: ${uri}`); }
});
await fs.writeFile(target, JSON.stringify(report, null, 2)+'\n');
console.log(JSON.stringify({ bytes: bytes.byteLength, errors: report.issues.numErrors, warnings: report.issues.numWarnings,
  infos: report.issues.numInfos, report: target }, null, 2));
if (report.issues.numErrors) process.exitCode = 1;
