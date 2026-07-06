import { existsSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const backendArtifacts = process.env.CINDER_BACKEND_ARTIFACTS ?? resolve(root, '..', 'backend', 'generated');
const openapi = resolve(backendArtifacts, 'openapi.json');
const documentSchema = resolve(backendArtifacts, 'cinder_simulation_case.schema.json');
const output = resolve(root, 'src', 'api', 'generated');

for (const file of [openapi, documentSchema]) {
  if (!existsSync(file)) {
    throw new Error(`Missing backend contract artifact: ${file}\nRun \`python -m app.scripts.export_contract_artifacts --output-dir generated\` from backend first, or set CINDER_BACKEND_ARTIFACTS.`);
  }
}

mkdirSync(output, { recursive: true });
const localBin = process.platform === 'win32' ? resolve(root, 'node_modules', '.bin', 'openapi-typescript.cmd') : resolve(root, 'node_modules', '.bin', 'openapi-typescript');
const localJson2Ts = process.platform === 'win32' ? resolve(root, 'node_modules', '.bin', 'json2ts.cmd') : resolve(root, 'node_modules', '.bin', 'json2ts');

function run(command, args) {
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit', shell: process.platform === 'win32' });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

run(localBin, [openapi, '--output', resolve(output, 'backend.ts')]);
run(localJson2Ts, [documentSchema, '--output', resolve(output, 'simulationCase.ts'), '--cwd', root]);
