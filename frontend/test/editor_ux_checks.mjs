import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let count = 0;
function test(name, fn) { fn(); count++; console.log('PASS', name); }

const modelFile = path.join(root, 'src/features/physicalLibrary/hardwareMeasurementKeys.ts');
const compiledModel = ts.transpileModule(fs.readFileSync(modelFile, 'utf8'), {
  fileName: modelFile,
  reportDiagnostics: true,
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true },
});
assert.equal(compiledModel.diagnostics?.filter((d) => d.category === ts.DiagnosticCategory.Error).length, 0, 'measurement-key syntax');
const modelContext = { exports: {} };
vm.runInNewContext(compiledModel.outputText, modelContext, { filename: modelFile });
const model = modelContext.exports;

test('geometry input paths map to the intended 3D measurement', () => {
  assert.equal(model.hardwareMeasurementKey('@primary-shaft-radius'), 'shaft-radius');
  assert.equal(model.hardwareMeasurementKey('/geometry/max_shift_m'), 'primary-travel');
  assert.equal(model.hardwareMeasurementKey('/geometry/deadzone_shift_m'), 'deadzone-travel');
  assert.equal(model.hardwareMeasurementKey('/pulleys/primary/components/0/geometry/pivot_radius_m'), 'pivot-radius');
  assert.equal(model.hardwareMeasurementKey('/pulleys/primary/components/0/geometry/arm_length_m'), 'arm-length');
  assert.equal(model.hardwareMeasurementKey('/inertias/primary/moving_sheave_mass_kg'), null);
});

test('hardware previews are real 3D pulley and flyweight views, not the old schematic', () => {
  const text = fs.readFileSync(path.join(root, 'src/features/physicalLibrary/CvtHardwarePreviews.tsx'), 'utf8');
  assert.match(text, /CVT_MODEL_IDS/);
  assert.match(text, /measuredPrimaryShaft/);
  assert.match(text, /Show reference ramp/);
  assert.match(text, /Reference ramp · adjusted in Tunes/);
  assert.match(text, /Shaft centreline/);
  assert.match(text, /Roller centre/);
  assert.match(text, /Reference arm pose only/);
});

test('CVT editor wires field focus into the two specialized 3D views', () => {
  const text = fs.readFileSync(path.join(root, 'src/features/physicalLibrary/CvtEditor.tsx'), 'utf8');
  assert.match(text, /onFocusChange=\{focusPath\(path\)\}/);
  assert.match(text, /onFocusChange=\{focusPath\('@primary-shaft-radius'\)\}/);
  assert.match(text, /<CvtPulleyPreview value=\{value\} activePath=\{focusedPath\} \/>/);
  assert.match(text, /<CvtPrimaryHardwarePreview value=\{value\} activePath=\{focusedPath\} \/>/);
  assert.doesNotMatch(text, /CvtMeasurementPreview/);
});

test('one Advanced section is assembled per top-level CVT category', () => {
  const text = fs.readFileSync(path.join(root, 'src/features/physicalLibrary/CvtEditor.tsx'), 'utf8');
  assert.match(text, /const groupedFields/);
  assert.match(text, /advanced\.length > 0/);
  assert.match(text, /value="primary"/);
  assert.match(text, /value="secondary"/);
});

test('new CVTs reuse TuneEditor controls for their initial\/default tune', () => {
  const text = fs.readFileSync(path.join(root, 'src/features/physicalLibrary/InitialTunePanel.tsx'), 'utf8');
  assert.match(text, /<TuneEditor/);
  assert.match(text, /previewRequest=\{previewRequest\}/);
  assert.match(text, /Apply to CVT/);
  assert.match(text, /first CVT save creates\s+its Default tune/i);
});

test('QuantityInput exposes focus state without changing its SI value contract', () => {
  const text = fs.readFileSync(path.join(root, 'src/components/quantityInput/QuantityInput.tsx'), 'utf8');
  assert.match(text, /onFocusChange\?: \(focused: boolean\) => void/);
  assert.match(text, /onFocusChange\?\.\(true\)/);
  assert.match(text, /onFocusChange\?\.\(false\)/);
  assert.match(text, /onChange\(next\.valueSi\)/);
});

for (const relative of [
  'src/features/physicalLibrary/CvtHardwarePreviews.tsx',
  'src/features/physicalLibrary/InitialTunePanel.tsx',
  'src/features/physicalLibrary/CvtEditor.tsx',
  'src/components/quantityInput/QuantityInput.tsx',
]) {
  const filename = path.join(root, relative);
  const parsed = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename,
    reportDiagnostics: true,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX, strict: true },
  });
  assert.equal(parsed.diagnostics?.filter((d) => d.category === ts.DiagnosticCategory.Error).length, 0, relative);
}

console.log(JSON.stringify({ editorUxChecks: count, syntaxFiles: 4 }));
