import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const filename = path.join(root, 'src/utils/units.ts');
const output = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  fileName: filename,
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true },
}).outputText;
const context = { exports: {}, Intl, console };
vm.runInNewContext(output, context, { filename });
const units = context.exports;
let count = 0;
function test(name, fn) { fn(); count++; console.log('PASS', name); }
function near(a, b, tolerance = 1e-12) { assert.ok(Math.abs(a - b) <= tolerance, `${a} != ${b}`); }

const p = text => units.parseQuantityText(text, 'length', 'in');
test('equivalent typed length units resolve to the same SI value', () => {
  const a = p('1.3in'), b = p('33.02 mm'), c = p('0.03302 m');
  assert.equal(a.error, undefined); assert.equal(b.error, undefined); assert.equal(c.error, undefined);
  near(a.valueSi, 0.03302); near(b.valueSi, a.valueSi); near(c.valueSi, a.valueSi);
});
test('simple inch fractions and mixed fractions are accepted', () => {
  near(p('1/2 in').valueSi, 0.0127);
  near(p('1 1/2in').valueSi, 0.0381);
  near(p('1-1/2"').valueSi, 0.0381);
});
test('a bare value or fraction uses the selected display unit', () => {
  near(p('2').valueSi, 0.0508);
  near(p('3/4').valueSi, 0.01905);
});
test('a dimension mismatch is rejected rather than guessed', () => {
  assert.match(p('10 kg').error, /length unit/);
});
test('recommended account defaults match the approved categories', () => {
  const recommended = units.presetUnitPreferences('recommended');
  assert.equal(recommended.hardware_length, 'in');
  assert.equal(recommended.component_mass, 'g');
  assert.equal(recommended.course_length, 'm');
  assert.equal(recommended.output_speed, 'km/h');
});
test('preference scopes can change display units without changing SI values', () => {
  const prefs = units.presetUnitPreferences('imperial');
  assert.equal(units.preferredDisplayUnit('length', 'hardware', prefs, 'mm'), 'in');
  assert.equal(units.preferredDisplayUnit('length', 'course', prefs, 'm'), 'ft');
  assert.equal(units.preferredDisplayUnit('speed', 'output', prefs, 'm/s'), 'mph');
  near(units.displayToSi(units.siToDisplay(0.03302, 'in'), 'in'), 0.03302);
});
console.log(JSON.stringify({ unitPreferenceAndParserChecks: count }));
