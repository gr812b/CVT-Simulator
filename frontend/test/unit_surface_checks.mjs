import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
import { fileURLToPath } from 'node:url';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const syntaxFiles = [
  'src/components/quantityInput/QuantityInput.tsx',
  'src/components/course/CourseChart.tsx',
  'src/features/physicalLibrary/VehicleEditor.tsx',
  'src/features/physicalLibrary/BeltEditor.tsx',
  'src/features/physicalLibrary/BeltPicker.tsx',
  'src/features/physicalLibrary/CvtEditor.tsx',
  'src/features/publicLibrary/ConfigurationView.tsx',
  'src/features/experiments/TuneEditor.tsx',
  'src/features/experiments/AngleProfileEditor.tsx',
  'src/features/experiments/ProfileSketch.tsx',
  'src/features/experiments/RoadEditor.tsx',
  'src/features/experiments/ScenarioEditor.tsx',
  'src/features/experiments/ExperimentPage.tsx',
  'src/pages/geometry/GeometryStudy.tsx',
  'src/pages/playback/reportGraphs.ts',
  'src/pages/playback/SimulationPlayback.tsx',
  'src/pages/playback/CoursePlayback.tsx',
  'src/features/results/runOutcome.ts',
  'src/features/results/RunOutcomeNotice.tsx',
  'src/features/experiments/RunActivity.tsx',
  'src/pages/dashboard/Dashboard.tsx',
  'src/features/results/RunHistory.tsx',
];

for (const relative of syntaxFiles) {
  const filename = path.join(frontend, relative);
  const parsed = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename,
    reportDiagnostics: true,
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext,
      jsx: ts.JsxEmit.ReactJSX,
      strict: true,
    },
  });
  const errors = parsed.diagnostics?.filter(
    diagnostic => diagnostic.category === ts.DiagnosticCategory.Error,
  ) ?? [];
  assert.equal(
    errors.length,
    0,
    `${relative}: ${errors.map(error => ts.flattenDiagnosticMessageText(error.messageText, '\n')).join('\n')}`,
  );
}

function loadTypescript(relative, dependencies = {}) {
  const filename = path.join(frontend, relative);
  const output = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename,
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS,
      strict: true,
    },
  }).outputText;
  const context = {
    exports: {},
    console,
    Intl,
    require(name) {
      if (!(name in dependencies)) throw new Error(`Unexpected runtime import: ${name}`);
      return dependencies[name];
    },
  };
  vm.runInNewContext(output, context, { filename });
  return context.exports;
}

const units = loadTypescript('src/utils/units.ts');
const reports = loadTypescript('src/pages/playback/reportGraphs.ts', {
  '@utils/units': units,
});
const imperial = units.presetUnitPreferences('imperial');
const table = {
  columns: [
    { key: 'time_s', dimension: 'time', canonical_unit: 's', values: [0, 1] },
    { key: 'vehicle.distance', dimension: 'length', canonical_unit: 'm', values: [0, 1] },
    { key: 'vehicle.speed', dimension: 'speed', canonical_unit: 'm/s', values: [0, 10] },
  ],
};
const before = JSON.stringify(table);
const categories = reports.buildReportGraphs(table, imperial);
assert.equal(JSON.stringify(table), before, 'graph conversion must not mutate canonical report data');
const kinematics = categories.find(category => category.title === 'Kinematics');
assert.ok(kinematics);
const distance = kinematics.graphs.find(graph => graph.config.title === 'Distance travelled');
const speed = kinematics.graphs.find(graph => graph.config.title === 'Vehicle speed');
assert.equal(distance.config.yAxis.unit, 'ft');
assert.ok(Math.abs(distance.yData[1][0] - 3.280839895013123) < 1e-10);
assert.equal(speed.config.yAxis.unit, 'mph');
assert.ok(Math.abs(speed.yData[1][0] - 22.369362920544) < 1e-10);

const quantity = fs.readFileSync(path.join(frontend, 'src/components/quantityInput/QuantityInput.tsx'), 'utf8');
assert.match(quantity, /entryUnit/, 'focused quantity text must retain its entry unit');
const playback = fs.readFileSync(path.join(frontend, 'src/pages/playback/SimulationPlayback.tsx'), 'utf8');
assert.match(playback, /downloadReportTableCsv\(table/, 'CSV export must keep using the canonical report table');
const cvt = fs.readFileSync(path.join(frontend, 'src/features/physicalLibrary/CvtEditor.tsx'), 'utf8');
assert.match(cvt, /scope="hardware"/);
const road = fs.readFileSync(path.join(frontend, 'src/features/experiments/RoadEditor.tsx'), 'utf8');
assert.match(road, /scope="course"/);

console.log(JSON.stringify({
  unitSurfaceSyntaxFiles: syntaxFiles.length,
  reportGraphPreferenceChecks: 4,
  canonicalReportMutationChecks: 1,
}));
