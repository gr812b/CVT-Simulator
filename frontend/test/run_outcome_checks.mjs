// Outcome presentation and the explicit partial-result polling contract.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const source = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../src');
function load(relative, dependencies = {}) {
  const filename = path.join(source, relative);
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const context = {
    exports: {}, console, Intl, setTimeout, DOMException,
    window: { setTimeout, clearTimeout },
    require(name) {
      if (!(name in dependencies)) throw Error(`Unexpected runtime import: ${name}`);
      return dependencies[name];
    },
  };
  vm.runInNewContext(code, context, { filename });
  return context.exports;
}
const { describeRunOutcome, outcomeDataMessage, outcomeProgress, outcomeLabel } =
  load('features/results/runOutcome.ts');
let count = 0;
async function test(name, fn) {
  await fn();
  count++;
  console.log('PASS', name);
}
const errorRun = {
  id: 'failed-run', status: 'failed', has_result: false,
  submitted_at: '2026-10-06T10:00:00Z', started_at: null, completed_at: '2026-10-06T10:00:01Z',
  error: { code: 'simulation_failed', message: 'RuntimeError: private implementation detail' },
};
const outcome = (changes = {}) => ({
  category: 'internal_error', reason: 'simulation_failed', severity: 'error',
  title: 'Simulation error', message: 'The simulation encountered an internal error.',
  action: 'Share this run ID with the maintainer.', has_data: false, partial: false,
  reached_time_s: null, reached_distance_m: null, support_run_id: errorRun.id,
  ...changes,
});

await test('an error before saved data gives no playback claim or invented progress', () => {
  const description = describeRunOutcome({ ...errorRun, outcome: outcome() });
  assert.match(outcomeDataMessage(description), /No simulation data was saved/);
  assert.equal(outcomeProgress(description), null);
  assert.doesNotMatch(JSON.stringify(description), /private implementation/);
});
await test('legacy raw exception messages are never shown as user diagnosis', () => {
  const description = describeRunOutcome(errorRun);
  assert.equal(description.category, 'internal_error');
  assert.doesNotMatch(description.message, /RuntimeError|private implementation/);
  assert.doesNotMatch(description.message, /invalid|your fault/i);
});
await test('partial numerical failures keep saved time, distance and export scope', () => {
  const description = describeRunOutcome({ ...errorRun, has_result: true,
    outcome: outcome({ category: 'numerical_error', has_data: true, partial: true,
      reached_time_s: 1.25, reached_distance_m: 6.5 }) });
  assert.match(outcomeProgress(description), /1\.25 s.*6\.5 m/);
  assert.match(outcomeDataMessage(description), /Partial result.*saved portion/);
  assert.equal(outcomeLabel(description), 'Solver error');
});
await test('a processed job that misses the course goal is not labelled completed', () => {
  const description = describeRunOutcome({ ...errorRun, status: 'completed', error: null,
    outcome: outcome({ category: 'vehicle_stopped', reason: 'no_forward_progress',
      severity: 'warning', has_data: true, partial: true }) });
  assert.equal(outcomeLabel(description), 'Course not completed');
  assert.notEqual(description.severity, 'success');
});
await test('a known model limit is distinct from invalid configuration and vehicle performance', () => {
  const description = outcome({ category: 'model_limit', reason: 'mechanism_contact_unsupported',
    severity: 'warning', message: 'The contact condition is outside the supported model.' });
  assert.equal(describeRunOutcome({ ...errorRun, outcome: description }), description);
  assert.equal(outcomeLabel(description), 'Model limit');
});
await test('known configuration, service, cancellation and resource outcomes retain server diagnosis', () => {
  for (const category of ['configuration_error', 'service_error', 'cancelled', 'resource_limit']) {
    const description = outcome({ category });
    assert.equal(describeRunOutcome({ ...errorRun, outcome: description }), description);
    assert.ok(outcomeLabel(description));
  }
});
await test('terminal errors override stale running checkpoint metadata', () => {
  const description = describeRunOutcome({ ...errorRun, has_result: true,
    summary_scalars: { metrics: { completed: false, termination_reason: 'running', duration_s: 0.5 } } });
  assert.equal(description.reason, 'simulation_failed');
  assert.equal(description.category, 'internal_error');
  assert.equal(description.partial, true);
  assert.doesNotMatch(description.message, /still running/);
});
await test('a stale pending outcome cannot keep a stopped job looking active', () => {
  const description = describeRunOutcome({ ...errorRun,
    outcome: outcome({ category: 'pending', reason: 'running', message: 'Still running' }) });
  assert.equal(description.category, 'internal_error');
  assert.doesNotMatch(description.message, /Still running/);
});
await test('legacy course stop metrics also prevent a success label', () => {
  const description = describeRunOutcome({ ...errorRun, status: 'completed', error: null,
    has_result: true, summary_scalars: { metrics: { completed: false, termination_reason: 'time_limit' } } });
  assert.equal(description.category, 'vehicle_stopped');
  assert.equal(description.partial, true);
});
await test('retained previews do not promise full playback after artifact eviction', () => {
  const description = outcome({ has_data: true, partial: true });
  assert.match(outcomeDataMessage(description, { preview: true, full_result: false, partial: true }),
    /saved preview.*Full playback.*unavailable/);
});
await test('a saved initial state is reported honestly, while non-finite progress is omitted', () => {
  assert.match(outcomeProgress(outcome({ has_data: true, reached_time_s: 0, reached_distance_m: 0 })), /0 s.*0 m/);
  assert.equal(outcomeProgress(outcome({ has_data: true, reached_time_s: NaN, reached_distance_m: Infinity })), null);
});

let responses = [], requests = 0;
class ApiClientError extends Error {}
const client = load('api/client.ts', {
  './transport': {
    ApiClientError,
    api: { GET: async () => {
      requests++;
      const data = responses.shift();
      if (!data) throw Error('Unexpected extra poll');
      return { data, response: { ok: true } };
    } },
    dataOrThrow: response => response.data,
  },
});
await test('the legacy client retains the additive outcome contract', async () => {
  responses = [{ ...errorRun, outcome: outcome() }];
  const run = await client.getSimulationRun(errorRun.id);
  assert.equal(run.outcome.support_run_id, errorRun.id);
  assert.equal(run.outcome.category, 'internal_error');
});
await test('failed runs with data still reject unless partial review is explicitly requested', async () => {
  responses = [{ ...errorRun, has_result: true, outcome: outcome({ has_data: true, partial: true }) }];
  await assert.rejects(client.waitForSimulationRun(errorRun.id), error =>
    error.name === 'SimulationRunError' && !/private implementation/.test(error.message));
});
await test('explicit partial review returns the failed lifecycle unchanged', async () => {
  responses = [{ ...errorRun, has_result: true, outcome: outcome({ has_data: true, partial: true }) }];
  const run = await client.waitForSimulationRun(errorRun.id, { allowPartial: true });
  assert.equal(run.status, 'failed');
  assert.equal(run.hasResult, true);
});
await test('allowing partial review cannot turn an error without data into a result', async () => {
  responses = [{ ...errorRun, outcome: outcome() }];
  await assert.rejects(client.waitForSimulationRun(errorRun.id, { allowPartial: true }), error =>
    error.name === 'SimulationRunError' && error.message.includes(errorRun.id));
});
await test('polling stops at one terminal partial result and preserves its reason', async () => {
  responses = [{ ...errorRun, status: 'running', error: null, completed_at: null, outcome: null },
    { ...errorRun, has_result: true, outcome: outcome({ category: 'model_limit', has_data: true, partial: true }) }];
  requests = 0;
  const run = await client.waitForSimulationRun(errorRun.id, { allowPartial: true, pollIntervalMs: 0 });
  assert.equal(requests, 2);
  assert.equal(run.outcome.category, 'model_limit');
  assert.equal(responses.length, 0);
});
console.log(JSON.stringify({ outcomeAndPollingChecks: count }));
