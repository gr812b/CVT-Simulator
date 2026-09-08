from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def require(path: str) -> Path:
    target = ROOT / path
    if not target.exists():
        raise SystemExit(f"Expected repository file not found: {path}\nRun this script from the extracted repository-root drop-in.")
    return target


def read(path: str) -> str:
    return require(path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"updated {path}")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one match in {path}, found {count}: {old[:100]!r}")
    write(path, text.replace(old, new, 1))


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    text = read(path)
    i = text.find(start)
    if i < 0:
        raise SystemExit(f"Start marker not found in {path}: {start!r}")
    j = text.find(end, i)
    if j < 0:
        raise SystemExit(f"End marker not found in {path}: {end!r}")
    write(path, text[:i] + replacement + text[j:])


# ---------------------------------------------------------------------------
# Backend: pin CINDER 1.1.1 and expose all CINDER-owned schemas.
# ---------------------------------------------------------------------------

requirements = read("backend/requirements.txt")
requirements = requirements.replace(
    "# After CINDER 1.1.0 is published, the follow-up integration PR changes only this pin.\n",
    "",
)
requirements = requirements.replace("cinder-cvt==1.0.1", "cinder-cvt==1.1.1")
write("backend/requirements.txt", requirements)

gateway_path = "backend/app/application/cinder_gateway.py"
gateway = read(gateway_path)
gateway = gateway.replace("import cinder.contracts as cinder_contracts\n", "")
if "SIMULATION_CASE_SCHEMA_VERSION" not in gateway.split("class CinderGateway", 1)[0]:
    gateway = gateway.replace(
        "from cinder.contracts import (\n",
        "from cinder.contracts import (\n"
        "    SIMULATION_CASE_SCHEMA_VERSION,\n"
        "    SIMULATION_RESULT_CONTRACT_VERSION,\n",
        1,
    )
if "assembly_document_json_schema," not in gateway.split("class CinderGateway", 1)[0]:
    gateway = gateway.replace(
        "    component_catalog_document,\n",
        "    assembly_document_json_schema,\n"
        "    component_catalog_document,\n",
        1,
    )
if "simulation_result_json_schema," not in gateway.split("class CinderGateway", 1)[0]:
    gateway = gateway.replace(
        "    simulation_case_document_json_schema,\n",
        "    simulation_case_document_json_schema,\n"
        "    simulation_result_json_schema,\n",
        1,
    )
write(gateway_path, gateway)

replace_between(
    gateway_path,
    "    def runtime_identity(self) -> dict[str, Any]:\n",
    "    def conventions(self) -> dict[str, Any]:\n",
    '''    def runtime_identity(self) -> dict[str, Any]:
        """Return the installed CINDER package and public contract versions."""

        return {
            "package": "cinder-cvt",
            "package_version": str(cinder.__version__),
            "simulation_case_schema_version": int(SIMULATION_CASE_SCHEMA_VERSION),
            "simulation_result_contract_version": int(
                SIMULATION_RESULT_CONTRACT_VERSION
            ),
        }

''',
)

replace_once(
    gateway_path,
    '''    def editor_schema(self) -> dict[str, Any]:
        return editable_simulation_case_schema()

    def simulation_case_json_schema(self) -> dict[str, Any]:
        return simulation_case_document_json_schema()
''',
    '''    def editor_schema(self) -> dict[str, Any]:
        return editable_simulation_case_schema()

    def assembly_json_schema(self) -> dict[str, Any]:
        return assembly_document_json_schema()

    def simulation_case_json_schema(self) -> dict[str, Any]:
        return simulation_case_document_json_schema()

    def simulation_result_json_schema(self) -> dict[str, Any]:
        return simulation_result_json_schema()
''',
)

write(
    "backend/app/scripts/export_contract_artifacts.py",
    '''"""Write ephemeral backend/CINDER contract artifacts for frontend type generation.

Run from the backend root after installing backend dependencies:

    python -m app.scripts.export_contract_artifacts --output-dir generated

The output directory is a build artifact, not source. OpenAPI describes backend
transport envelopes; CINDER's schemas describe the nested assembly, simulation
case, and simulation result contracts without the backend duplicating them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.application.cinder_gateway import CinderGateway
from app.main import create_app


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="generated")
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    gateway = CinderGateway()
    _write_json(output / "openapi.json", create_app().openapi())
    _write_json(output / "cinder_assembly.schema.json", gateway.assembly_json_schema())
    _write_json(
        output / "cinder_simulation_case.schema.json",
        gateway.simulation_case_json_schema(),
    )
    _write_json(
        output / "cinder_simulation_result.schema.json",
        gateway.simulation_result_json_schema(),
    )


if __name__ == "__main__":
    main()
''',
)

# ---------------------------------------------------------------------------
# Frontend type generation: all CINDER schemas + local auto-refresh.
# ---------------------------------------------------------------------------

package_path = ROOT / "frontend/package.json"
package = json.loads(package_path.read_text(encoding="utf-8"))
old_scripts = package["scripts"]
package["scripts"] = {
    "predev": "npm run contracts:generate",
    "dev": old_scripts["dev"],
    "prebuild": "npm run contracts:generate",
    "build": old_scripts["build"],
    "lint": old_scripts["lint"],
    "preview": old_scripts["preview"],
    "contracts:generate": old_scripts["contracts:generate"],
}
write("frontend/package.json", json.dumps(package, indent=2) + "\n")

write(
    "frontend/scripts/generate-contracts.mjs",
    r'''import { appendFileSync, existsSync, mkdirSync, rmSync } from 'node:fs';
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
''',
)

# ---------------------------------------------------------------------------
# Frontend: use generated CINDER result type directly instead of duplicating it.
# ---------------------------------------------------------------------------

client_path = "frontend/src/api/client.ts"
client = read(client_path)
if "./generated/simulationResult" not in client:
    client = client.replace(
        "import type { CINDERSimulationCaseDocument } from './generated/simulationCase';\n",
        "import type { CINDERSimulationCaseDocument } from './generated/simulationCase';\n"
        "import type { CINDERSimulationResultDocument } from './generated/simulationResult';\n",
        1,
    )
write(client_path, client)

replace_between(
    client_path,
    "export interface ReportColumn {\n",
    "export interface CompletedSimulationRun {\n",
    '''export type SimulationResult = CINDERSimulationResultDocument;
export type ReportTable = SimulationResult['report_table'];
export type ReportColumn = ReportTable['columns'][number];
export type SimulationTransition = SimulationResult['transitions'][number];

''',
)

replace_between(
    client_path,
    "function parseReportColumn(raw: unknown): ReportColumn {\n",
    "\n\n\nexport async function listVehicleAssemblies",
    '''function parseSimulationResult(raw: unknown): SimulationResult {
  const value = object(raw, 'simulation result');
  if (value.kind !== 'simulation_result') throw new ApiClientError('Unexpected result kind.');
  return value as unknown as SimulationResult;
}
''',
)

write(
    "frontend/src/utils/reportTable.ts",
    '''import type { ReportColumn, ReportTable } from '@api/client';

export function reportColumn(table: ReportTable, key: string): ReportColumn | undefined {
  return table.columns.find((column) => column.key === key);
}

export function requireReportColumn(table: ReportTable, key: string): ReportColumn {
  const column = reportColumn(table, key);
  if (column === undefined) throw new Error(`CINDER report table does not contain '${key}'.`);
  return column;
}

export function reportAxisTimes(table: ReportTable): number[] {
  const axis = requireReportColumn(table, table.axis_key);
  if (axis.values.length !== table.row_count) {
    throw new Error(`CINDER report axis '${table.axis_key}' has ${axis.values.length} rows; expected ${table.row_count}.`);
  }
  let previous = 0;
  return axis.values.map((value, index) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      throw new Error(`CINDER report axis '${table.axis_key}' contains a non-finite time at row ${index}.`);
    }
    if (index > 0 && value < previous) {
      throw new Error(`CINDER report axis '${table.axis_key}' is not time ordered at row ${index}.`);
    }
    previous = value;
    return value;
  });
}

export function reportValue(column: ReportColumn | undefined, index: number): number | null {
  if (column === undefined || index < 0 || index >= column.values.length) return null;
  return column.values[index];
}

export function numericPairs(table: ReportTable, xKey: string, yKey: string): Array<[number, number]> {
  const x = reportColumn(table, xKey);
  const y = reportColumn(table, yKey);
  if (x === undefined || y === undefined) return [];
  const count = Math.min(x.values.length, y.values.length);
  const pairs: Array<[number, number]> = [];
  for (let index = 0; index < count; index += 1) {
    const xValue = x.values[index];
    const yValue = y.values[index];
    if (xValue !== null && yValue !== null) pairs.push([xValue, yValue]);
  }
  return pairs;
}

export function reportRows(table: ReportTable): Array<Record<string, number | null>> {
  return Array.from({ length: table.row_count }, (_, index) => Object.fromEntries(
    table.columns.map((column) => [column.key, column.values[index] ?? null]),
  ));
}

export function valueAt(table: ReportTable, key: string, index: number): number | null {
  return reportValue(reportColumn(table, key), index);
}
''',
)

write(
    "frontend/src/utils/csvExport.ts",
    '''import type { ReportTable } from '@api/client';

function escapeCsv(value: string | number | null): string {
  const text = value === null ? '' : String(value);
  return /[",\\n\\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** Export exactly the CINDER report-table columns; no legacy nested-output flattening. */
export function downloadReportTableCsv(table: ReportTable, filePrefix = 'cinder_simulation_report'): void {
  const header = table.columns.map((column) => `${column.key} [${column.canonical_unit}]`);
  const rows = Array.from({ length: table.row_count }, (_, row) => table.columns.map((column) => column.values[row] ?? null));
  const csv = [header, ...rows].map((row) => row.map(escapeCsv).join(',')).join('\\r\\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${filePrefix}_${new Date().toISOString().replace(/[:.]/g, '-')}.csv`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
''',
)

replace_once(
    "frontend/src/pages/playback/Playback.tsx",
    "const navigate = useNavigate(); const table = run.result.reportTable;",
    "const navigate = useNavigate(); const table = run.result.report_table;",
)
replace_once(
    "frontend/src/pages/playback/reportGraphs.ts",
    "    : columnValue.canonicalUnit;",
    "    : columnValue.canonical_unit;",
)
replace_once(
    "frontend/src/components/scene3DViewer/Scene3DViewer.tsx",
    "  const timeKey = table.axisKey;",
    "  const timeKey = table.axis_key;",
)

# ---------------------------------------------------------------------------
# Generated artifacts are build outputs, not source.
# ---------------------------------------------------------------------------

gitignore_path = ".gitignore"
gitignore = read(gitignore_path)
block = "\n# Generated API/CINDER contract artifacts\nbackend/generated/\nfrontend/src/api/generated/\n"
if "frontend/src/api/generated/" not in gitignore:
    gitignore = gitignore.rstrip() + "\n" + block
    write(gitignore_path, gitignore)

root_dockerignore = read(".dockerignore")
docker_block = "\n# Local/generated contract and environment artifacts\n**/venv/\nbackend/generated/\nfrontend/src/api/generated/\n"
if "frontend/src/api/generated/" not in root_dockerignore:
    root_dockerignore = root_dockerignore.rstrip() + "\n" + docker_block
    write(".dockerignore", root_dockerignore)

# Remove already tracked generated artifacts from the index. They will be
# regenerated on demand and ignored from now on.
try:
    subprocess.run(
        [
            "git",
            "rm",
            "-r",
            "--cached",
            "--ignore-unmatch",
            "backend/generated",
            "frontend/src/api/generated",
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print("untracked backend/generated and frontend/src/api/generated")
except (FileNotFoundError, subprocess.CalledProcessError) as error:
    print(f"warning: could not update git index for generated artifacts: {error}")

for generated_dir in (ROOT / "backend/generated", ROOT / "frontend/src/api/generated"):
    if generated_dir.exists():
        shutil.rmtree(generated_dir)
        print(f"removed working build artifact {generated_dir.relative_to(ROOT)}")

# ---------------------------------------------------------------------------
# CI/build pipeline: generate instead of checking committed generated files.
# ---------------------------------------------------------------------------

replace_between(
    ".github/workflows/ci.yaml",
    "      - name: Verify generated frontend contracts are current\n",
    "      - name: Run ESLint\n",
    '''      - name: Generate frontend contracts
        run: npm --prefix frontend run contracts:generate

''',
)

replace_once(
    ".github/workflows/containerize.yaml",
    "          context: ./frontend\n          file: ./frontend/Dockerfile\n",
    "          context: .\n          file: ./frontend/Dockerfile\n",
)

write(
    "frontend/Dockerfile",
    '''# Build context: repository root.
# CINDER/backend contracts are generated in an isolated build stage, then the
# TypeScript client is generated before the Vite build. Generated contracts do
# not need to be committed to the repository.

FROM python:3.10-slim AS contracts

WORKDIR /repo/backend
COPY backend/requirements.txt ./requirements.txt
RUN python -m venv /opt/venv \\
    && /opt/venv/bin/python -m pip install --upgrade pip \\
    && /opt/venv/bin/python -m pip install -r requirements.txt
COPY backend/ ./
RUN /opt/venv/bin/python -m app.scripts.export_contract_artifacts --output-dir /contracts

FROM node:20-alpine AS build

WORKDIR /app

# Vite embeds VITE_* values at build time. Leave this blank for the default
# production deployment: the browser calls same-origin /api/v1/* and nginx
# proxies those requests to the backend container.
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV CINDER_BACKEND_ARTIFACTS=/contracts

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
COPY --from=contracts /contracts /contracts
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
''',
)

# ---------------------------------------------------------------------------
# Documentation cleanup.
# ---------------------------------------------------------------------------

architecture = read("backend/docs/ARCHITECTURE.md")
old_arch = '''Current CINDER v1 releases expose one `PUBLIC_CONTRACT_VERSION`. The gateway
therefore uses it as a compatibility fallback. A CINDER release that evolves the
contracts independently can expose `SIMULATION_CASE_SCHEMA_VERSION` and
`SIMULATION_RESULT_CONTRACT_VERSION`; in particular, a result-only change can
leave the saved input document at schema v1 while the result projection advances
to v2.'''
new_arch = '''CINDER exposes `SIMULATION_CASE_SCHEMA_VERSION` and
`SIMULATION_RESULT_CONTRACT_VERSION` directly. The backend pins one exact CINDER
package version and does not carry compatibility aliases for older package
contracts.

CINDER also owns machine-readable JSON Schema for its assembly, simulation-case,
and simulation-result documents. `export_contract_artifacts` writes those
schemas together with backend OpenAPI as ephemeral build artifacts. Frontend
TypeScript generation consumes them directly; the backend does not re-declare
CINDER result/domain/field structures.'''
if old_arch in architecture:
    architecture = architecture.replace(old_arch, new_arch)
    write("backend/docs/ARCHITECTURE.md", architecture)

frontend_readme = read("frontend/README.md")
frontend_readme = frontend_readme.replace(
    '''When the backend OpenAPI contract changes, regenerate and commit the generated types:

```powershell
npm run contracts:generate
```
''',
    '''API/CINDER TypeScript contracts are generated build artifacts and are not committed.
`npm run dev` and `npm run build` refresh them automatically. The generator uses
`backend/venv` when available (or `CINDER_BACKEND_PYTHON` / system Python) to
export backend OpenAPI plus CINDER assembly, simulation-case, and
simulation-result schemas before generating TypeScript.

You can still regenerate explicitly when debugging the contract boundary:

```powershell
npm run contracts:generate
```
''',
)
frontend_readme = frontend_readme.replace(
    "docker build -f frontend/Dockerfile -t cvt-simulator-frontend frontend",
    "docker build -f frontend/Dockerfile -t cvt-simulator-frontend .",
)
frontend_readme = frontend_readme.replace(
    '''docker build -f frontend/Dockerfile `
  --build-arg VITE_API_BASE_URL=https://api.example.com `
  -t cvt-simulator-frontend frontend''',
    '''docker build -f frontend/Dockerfile `
  --build-arg VITE_API_BASE_URL=https://api.example.com `
  -t cvt-simulator-frontend .''',
)
write("frontend/README.md", frontend_readme)

print("\nDrop-in applied successfully.")
print("Backend is now pinned to cinder-cvt==1.1.1.")
print("Generated contracts are untracked and will be recreated automatically.")
print("If backend/venv already exists, refresh it once with: python -m pip install -r backend/requirements.txt")
