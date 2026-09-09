import { appendFileSync, existsSync, mkdirSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repositoryRoot = resolve(frontendRoot, '..');
const backendRoot = resolve(repositoryRoot, 'backend');
const backendArtifacts = process.env.CINDER_BACKEND_ARTIFACTS ?? resolve(backendRoot, 'generated');

const inputs = {
  openapi: resolve(backendArtifacts, 'openapi.json'),
  assembly: resolve(backendArtifacts, 'cinder_assembly.schema.json'),
  simulationCase: resolve(backendArtifacts, 'cinder_simulation_case.schema.json'),
  simulationResult: resolve(backendArtifacts, 'cinder_simulation_result.schema.json'),
};

const output = resolve(frontendRoot, 'src', 'api', 'generated');
const outputs = {
  backend: resolve(output, 'backend.ts'),
  assembly: resolve(output, 'assembly.ts'),
  simulationCase: resolve(output, 'simulationCase.ts'),
  simulationResult: resolve(output, 'simulationResult.ts'),
};

const executable = (name) => process.platform === 'win32'
  ? resolve(frontendRoot, 'node_modules', '.bin', `${name}.cmd`)
  : resolve(frontendRoot, 'node_modules', '.bin', name);

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? frontendRoot,
    stdio: 'inherit',
    shell: process.platform === 'win32' && !command.toLowerCase().endsWith('.exe'),
    env: process.env,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

function allExist(paths) {
  return paths.every((path) => existsSync(path));
}

function backendPython() {
  const explicit = process.env.CINDER_BACKEND_PYTHON;
  if (explicit) return explicit;

  const venvPython = process.platform === 'win32'
    ? resolve(backendRoot, 'venv', 'Scripts', 'python.exe')
    : resolve(backendRoot, 'venv', 'bin', 'python');
  if (existsSync(venvPython)) return venvPython;

  return process.platform === 'win32' ? 'python' : 'python3';
}

function refreshBackendArtifactsForLocalDevelopment() {
  if (process.env.CINDER_BACKEND_ARTIFACTS) return;
  if (process.env.CINDER_SKIP_BACKEND_EXPORT === '1') return;
  if (!existsSync(backendRoot)) return;
  if (process.env.CI === 'true') return;

  console.log('Refreshing backend/CINDER contract artifacts...');
  run(
    backendPython(),
    ['-m', 'app.scripts.export_contract_artifacts', '--output-dir', 'generated'],
    { cwd: backendRoot },
  );
}

refreshBackendArtifactsForLocalDevelopment();

const inputPaths = Object.values(inputs);
const outputPaths = Object.values(outputs);
if (!allExist(inputPaths)) {
  // Frontend-only Docker stages may receive already-generated TS without the
  // backend source. In every normal repository/CI path the schemas are present.
  if (allExist(outputPaths)) {
    console.log('Backend contract artifacts are unavailable; using pre-generated frontend contracts.');
    process.exit(0);
  }
  const missing = inputPaths.filter((path) => !existsSync(path));
  throw new Error(
    `Missing contract artifacts:\n${missing.map((path) => `  - ${path}`).join('\n')}\n` +
    'Install backend dependencies (including the pinned CINDER release) and rerun this command.',
  );
}

rmSync(output, { recursive: true, force: true });
mkdirSync(output, { recursive: true });

run(executable('openapi-typescript'), [inputs.openapi, '--output', outputs.backend]);
run(executable('json2ts'), [inputs.assembly, '--output', outputs.assembly, '--cwd', frontendRoot]);
run(executable('json2ts'), [inputs.simulationCase, '--output', outputs.simulationCase, '--cwd', frontendRoot]);
run(executable('json2ts'), [inputs.simulationResult, '--output', outputs.simulationResult, '--cwd', frontendRoot]);

// Stable import names keep application code independent of schema-title naming.
appendFileSync(outputs.assembly, '\nexport type CINDERAssemblyDocument = CINDERCVTAssembly;\n', 'utf8');
appendFileSync(
  outputs.simulationCase,
  '\nexport type CINDERSimulationCaseDocument = CINDERComposedCVTSimulationCase;\n',
  'utf8',
);
appendFileSync(
  outputs.simulationResult,
  '\nexport type CINDERSimulationResultDocument = CINDERSimulationResult;\n',
  'utf8',
);
