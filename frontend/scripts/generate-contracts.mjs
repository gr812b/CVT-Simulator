#!/usr/bin/env node
/** Regenerate the generated contracts committed under src/api/generated. */
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const backendRoot = resolve(process.env.CVT_BACKEND_DIR ?? resolve(frontendRoot, '../backend'));
const openapi = resolve(process.env.CVT_OPENAPI_SCHEMA ?? resolve(backendRoot, 'generated/openapi.json'));
const cinderSchema = resolve(process.env.CVT_CINDER_SCHEMA ?? resolve(backendRoot, 'generated/cinder_simulation_case.schema.json'));
const output = resolve(frontendRoot, 'src/api/generated');
for (const artifact of [openapi, cinderSchema]) if (!existsSync(artifact)) throw new Error(`Contract artifact not found: ${artifact}`);
mkdirSync(output, { recursive: true });
const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';
function run(args) { const result = spawnSync(npx, ['--no-install', ...args], { cwd: frontendRoot, stdio: 'inherit' }); if (result.status !== 0) process.exit(result.status ?? 1); }
run(['openapi-typescript', openapi, '-o', resolve(output, 'backend.ts')]);
run(['json-schema-to-typescript', cinderSchema, '-o', resolve(output, 'simulationCase.ts'), '--unknownAny']);
