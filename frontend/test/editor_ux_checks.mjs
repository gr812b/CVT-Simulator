import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let count = 0;
function test(name, fn) { fn(); count++; console.log('PASS', name); }

const modelFile = path.join(root, 'src/features/physicalLibrary/cvtMeasurementPreviewModel.ts');
const compiledModel = ts.transpileModule(fs.readFileSync(modelFile, 'utf8'), {
  fileName: modelFile,
  reportDiagnostics: true,
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true },
});
assert.equal(compiledModel.diagnostics?.filter((d) => d.category === ts.DiagnosticCategory.Error).length, 0, 'preview model syntax');
const modelContext = { exports: {} };
vm.runInNewContext(compiledModel.outputText, modelContext, { filename: modelFile });
const model = modelContext.exports;

test('geometry input paths map to the intended highlighted measurement', () => {
  assert.equal(model.cvtMeasurementKeyForPath('@primary-shaft-radius'), 'shaft-radius');
  assert.equal(model.cvtMeasurementKeyForPath('/geometry/max_shift_m'), 'primary-travel');
  assert.equal(model.cvtMeasurementKeyForPath('/geometry/deadzone_shift_m'), 'deadzone-travel');
  assert.equal(model.cvtMeasurementKeyForPath('/pulleys/primary/components/0/geometry/pivot_radius_m'), 'pivot-radius');
  assert.equal(model.cvtMeasurementKeyForPath('/pulleys/primary/components/0/geometry/arm_length_m'), 'arm-length');
  assert.equal(model.cvtMeasurementKeyForPath('/inertias/primary/moving_sheave_mass_kg'), null);
});

test('preview source keeps ramp start distinct from solved roller contact', () => {
  const text = fs.readFileSync(path.join(root, 'src/features/physicalLibrary/CvtMeasurementPreview.tsx'), 'utf8');
  assert.match(text, /Ramp start · Tunes/);
  assert.match(text, /roller contact is solved separately/i);
  assert.match(text, /Roller pose is schematic/i);
  assert.match(text, /Shaft centreline/);
  assert.match(text, /Belt surfaces/);
  assert.match(text, /Movable-sheave travel/);
});

test('CVT editor wires quantity focus into the measurement guide', () => {
  const text = fs.readFileSync(path.join(root, 'src/features/physicalLibrary/CvtEditor.tsx'), 'utf8');
  assert.match(text, /onFocusChange=\{focusPath\(path\)\}/);
  assert.match(text, /onFocusChange=\{focusPath\('@primary-shaft-radius'\)\}/);
  assert.match(text, /<CvtMeasurementPreview value=\{value\} activePath=\{focusedPath\} \/>/);
});

test('QuantityInput exposes focus state without changing its SI value contract', () => {
  const text = fs.readFileSync(path.join(root, 'src/components/quantityInput/QuantityInput.tsx'), 'utf8');
  assert.match(text, /onFocusChange\?: \(focused: boolean\) => void/);
  assert.match(text, /onFocusChange\?\.\(true\)/);
  assert.match(text, /onFocusChange\?\.\(false\)/);
  assert.match(text, /onChange\(candidate\.valueSi\)/);
});

for (const relative of [
  'src/features/physicalLibrary/CvtMeasurementPreview.tsx',
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

console.log(JSON.stringify({ editorUxChecks: count, syntaxFiles: 3 }));
