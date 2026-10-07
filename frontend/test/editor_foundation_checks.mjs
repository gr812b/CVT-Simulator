// Pure production modules, not copies of the parser/history implementation.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../src');
const cache = new Map();
function load(relative) {
  const filename = path.resolve(root, relative);
  if (cache.has(filename)) return cache.get(filename);
  const output = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename, compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const context = { exports: {}, Intl, structuredClone, console, require(name) {
    if (!name.startsWith('.')) throw Error(`Unexpected runtime dependency: ${name}`);
    const resolved = path.resolve(path.dirname(filename), name);
    return load(resolved.endsWith('.ts') ? resolved : resolved + '.ts');
  } };
  vm.runInNewContext(output, context, { filename });
  cache.set(filename, context.exports);
  return context.exports;
}
const U = load('utils/units.ts');
const { displayColumn, convertZoomUnits } = load('utils/unitProjection.ts');
const { DraftHistory } = load('components/editorHistory/draftHistory.ts');
const { editQuantity } = load('components/quantityInput/quantityDraft.ts');
const { withBeltPreservingPrimaryShaft, primaryShaftRadius } = load('features/physicalLibrary/cvtHardware.ts');
const near = (a,b) => assert.ok(Math.abs(a-b) <= 1e-12*Math.max(1,Math.abs(b)), `${a} != ${b}`);
const plain = value => JSON.parse(JSON.stringify(value));
let count = 0;
function test(name, fn) { fn(); count++; console.log('PASS', name); }
const parse = (text, dimension='length', unit='in') => U.parseQuantityText(text,dimension,unit);
test('all requested equivalent lengths, fractions and scientific notation', () => {
  for (const value of ['1.3in','33.02 mm','0.03302 m','3.302e-2 m']) near(parse(value).valueSi,.03302);
  for (const value of ['1 1/2 in','1-1/2"','1.5 inches']) near(parse(value).valueSi,.0381);
  near(parse('-0 1/2 in').valueSi,-.0127);
});
test('pending text, incompatible units and nonfinite numbers fail closed', () => {
  for (const value of ['', '-', '1e-', '1/0 in', 'NaN', '1e999 m', '3 kg', '3.1.2', '1 + 2 m'])
    assert.ok(parse(value).error, value);
});
test('linear and torsional stiffness cannot be mixed', () => {
  assert.ok(parse('10 N/mm','torsional_stiffness','N·m/rad').error);
  assert.ok(parse('10 N·m/rad','stiffness','N/mm').error);
  near(parse('10 N/mm','stiffness','N/m').valueSi,10000);
  near(parse('1 N·m/deg','torsional_stiffness','N·m/rad').valueSi,180/Math.PI);
});
test('length rates and speed share physical compatibility, not preference scopes', () => {
  near(parse('10 mm/s','speed','m/s').valueSi,.01);
  near(parse('0.01 m/s','length_rate','mm/s').valueSi,.01);
  near(parse('36 km/h','length_rate','in/s').valueSi,10);
});
test('area conversion squares the length factor; inertia distinguishes mass and force', () => {
  near(parse('1 in2','area','m²').valueSi,.0254**2);
  near(parse('1 kg·mm²','inertia','kg·m²').valueSi,1e-6);
  near(parse('1 g*mm^2','inertia','kg·m²').valueSi,1e-9);
  near(parse('1 lbm·in²','inertia','kg·m²').valueSi,.45359237*.0254**2);
  assert.ok(parse('1 lbf·in','inertia','kg·m²').error);
});
test('every supported unit round-trips in its physical dimension', () => {
  for (const [unit,[dimension]] of Object.entries(U.UNIT_CATALOG)) {
    near(U.displayToSi(U.siToDisplay(.3125,unit),unit),.3125);
    near(parse(`2 ${unit}`,dimension,unit).valueSi,U.displayToSi(2,unit));
  }
});
test('recommended inertia remains SI regardless of hardware length', () => {
  const p = U.normalizeUnitPreferences({hardware_length:'in'});
  assert.equal(U.preferredDisplayUnit('inertia','hardware',p),'kg·m²');
  assert.equal(U.preferredDisplayUnit('area','vehicle',p),'m²');
  assert.equal(U.preferredDisplayUnit('mass','hardware',p),'g');
});
test('overrides are scoped and rejected safely when dimensionally invalid', () => {
  const p=U.normalizeUnitPreferences({quantity_units:{hardware:{inertia:'g·mm²',area:'in²'},output:{inertia:'kg·mm²',area:'ft²'},vehicle:{area:'kg'}}});
  assert.equal(U.preferredDisplayUnit('inertia','hardware',p),'g·mm²');
  assert.equal(U.preferredDisplayUnit('inertia','output',p),'kg·mm²');
  assert.equal(U.preferredDisplayUnit('area','vehicle',p),'m²');
  const b=U.normalizeUnitPreferences(null); assert.deepEqual(plain(b.quantity_units),{});
});
test('presets produce independent nested preferences', () => {
  const p=U.presetUnitPreferences('imperial'), q=U.presetUnitPreferences('imperial');
  p.quantity_units.hardware.inertia='kg·m²';
  assert.equal(q.quantity_units.hardware.inertia,'lbm·in²');
  assert.equal(U.normalizeUnitPreferences({preset:'invalid'}).preset,'recommended');
});
test('old generic report stiffness resolves from its canonical unit', () => {
  const p=U.normalizeUnitPreferences({quantity_units:{output:{torsional_stiffness:'N·m/deg'}}});
  assert.equal(U.preferredProjectedDisplayUnit('stiffness','N·m/rad','output',p),'N·m/deg');
  near(U.projectedDisplayValue(1,'stiffness','N·m/rad','output',p),Math.PI/180);
});
test('small metric plot labels retain distinct nonzero measurements', () => {
  const labels=[0,.02,.04].map(v=>U.formatDisplayNumber(v,1));
  assert.equal(new Set(labels).size,3); assert.equal(labels[1],'0.02');
  assert.notEqual(U.formatDisplayNumber(1e-12,1),'0');
});
test('untouched formatting cannot alter a canonical number', () => {
  const value=.0032202838346490647;
  const h=new DraftHistory({value});
  for (const unit of ['kg·m²','kg·mm²','g·mm²','lbm·in²']) U.formatEditableQuantity(value,unit);
  assert.equal(h.getSnapshot().value.value,value);
  assert.equal(h.getSnapshot().dirty,false);assert.equal(h.getSnapshot().canUndo,false);
});
test('ranges and whole-number constraints are evaluated after SI conversion', () => {
  assert.ok(editQuantity('2 in','length','mm',0,{max:.03}).error);
  assert.ok(editQuantity('1.5','dimensionless','',1,{integer:true}).error);
  assert.equal(editQuantity('33.02 mm','length','in',.03302,{}).valueSi,.03302);
});
test('grouped text editing is one undo with raw invalid text included', () => {
  const h=new DraftHistory({length:.02});
  h.beginGroup('length');
  for(const text of ['3','30','30 m','broken']) h.transaction(()=>{
    const draft=editQuantity(text,'length','mm',h.getSnapshot().value.length,{});
    h.setQuantity('length',draft);
    if(!draft.error)h.setValue({length:draft.valueSi});
  });
  h.endGroup();assert.equal(h.getSnapshot().invalidCount,1);
  h.undo(); assert.equal(h.getSnapshot().value.length,.02);assert.equal(h.getSnapshot().dirty,false);
  h.redo();assert.equal(h.getSnapshot().quantities.length.text,'broken');assert.equal(h.getSnapshot().invalidCount,1);
});
test('separate operations remain independently undoable', () => {
  const h=new DraftHistory({x:1,y:1});
  h.setValue({x:2,y:1});h.setValue({x:2,y:3});h.undo();assert.deepEqual(plain(h.getSnapshot().value),{x:2,y:1});
  h.undo();assert.deepEqual(plain(h.getSnapshot().value),{x:1,y:1});
});
test('save establishes baseline and keeps session history; failed save does nothing', () => {
  const h=new DraftHistory({x:1});h.setValue({x:2});h.markSaved({x:2});
  assert.equal(h.getSnapshot().dirty,false);h.undo();assert.equal(h.getSnapshot().value.x,1);assert.equal(h.getSnapshot().dirty,true);
  h.redo();assert.equal(h.getSnapshot().dirty,false);
  h.setValue({x:3});assert.equal(h.getSnapshot().dirty,true); // no reset on failure
});
test('discard resets raw text, history and dirty state', () => {
  const h=new DraftHistory({x:1});h.setQuantity('x',editQuantity('-','mass','g',1,{}));
  h.reset({x:1});assert.equal(h.getSnapshot().invalidCount,0);assert.equal(h.getSnapshot().dirty,false);assert.equal(h.getSnapshot().canUndo,false);
});
test('same-value edit produces no canonical drift or redundant history', () => {
  const h=new DraftHistory({length:.03302});h.beginGroup('x');
  h.setQuantity('x',editQuantity('1.3 in','length','in',.03302,{}));h.setQuantity('x',undefined);h.endGroup();
  assert.equal(h.getSnapshot().canUndo,false);assert.equal(h.getSnapshot().dirty,false);
});
test('new edit after undo clears redo; transaction exceptions roll back', () => {
  const h=new DraftHistory({x:1});h.setValue({x:2});h.undo();h.setValue({x:3});assert.equal(h.getSnapshot().canRedo,false);
  assert.throws(()=>h.transaction(()=>{h.setValue({x:4});throw Error('reject');}));assert.equal(h.getSnapshot().value.x,3);
});
test('removing/replacing a profile and its invalid text is one operation', () => {
  const h=new DraftHistory({profile:[1,2]});h.setQuantity('profile:1',editQuantity('bad','length','in',2,{}));
  h.transaction(()=>{h.clearQuantities('profile:');h.setValue({profile:[1]});});
  assert.equal(h.getSnapshot().invalidCount,0);h.undo();assert.equal(h.getSnapshot().invalidCount,1);assert.equal(h.getSnapshot().value.profile.length,2);
});
test('field removal prunes only its raw state and undo restores both', () => {
  const h=new DraftHistory({a:1,b:2});h.setQuantity('a',editQuantity('bad','mass','kg',1,{},'/a'));
  h.setValue({b:2});assert.equal(h.getSnapshot().invalidCount,0);h.undo();assert.equal(h.getSnapshot().invalidCount,1);
});
const belt=(height)=>({name:'Belt',data:{height_m:height,outer_length_m:.95,outer_width_m:.02+2*height*Math.tan(.3),inner_width_m:.02,cord_depth_from_outer_m:.003,half_angle_rad:.3,density_kg_per_m3:1100,length_reference:'outer'}});
const initial={belt:belt(.015),assembly:{geometry:{primary_outer_radius_at_zero_shift_m:.04,belt:{height_m:.015}},inertias:{belt_density_kg_per_m3:1000}}};
test('belt selection updates embedded section, selected section, length, angle and density together', () => {
  const old=JSON.stringify(initial), next=withBeltPreservingPrimaryShaft(initial,belt(.02));
  near(primaryShaftRadius(next),.025);assert.equal(next.assembly.geometry.belt.height_m,.02);
  assert.equal(next.assembly.geometry.belt_outer_length_m,.95);
  assert.equal(next.assembly.inertias.belt_density_kg_per_m3,1100);
  assert.equal(next.assembly.geometry.belt.density_kg_per_m3,undefined);assert.equal(JSON.stringify(initial),old);
});
test('belt swap and all induced geometry values undo/redo atomically', () => {
  const h=new DraftHistory(initial);const next=withBeltPreservingPrimaryShaft(h.getSnapshot().value,belt(.02));
  h.setValue(next);h.undo();assert.deepEqual(plain(h.getSnapshot().value),initial);
  h.redo();assert.deepEqual(plain(h.getSnapshot().value),plain(next));
});
test('same-height belt selection preserves the outer radius bit-for-bit', () => {
  const cvt=structuredClone(initial);cvt.assembly.geometry.primary_outer_radius_at_zero_shift_m=.043220283834649065;
  const next=withBeltPreservingPrimaryShaft(cvt,belt(.015));
  assert.equal(next.assembly.geometry.primary_outer_radius_at_zero_shift_m,cvt.assembly.geometry.primary_outer_radius_at_zero_shift_m);
});
test('frontend preference catalog and backend validation choices agree exactly', () => {
  const backend = JSON.parse(fs.readFileSync(path.resolve(root, '../../backend/app/schemas/unit_choices.json'),'utf8'));
  const catalog = Object.fromEntries(['hardware','vehicle','course','output'].map(scope=>[scope,
    Object.fromEntries(U.extraPreferenceDimensions(scope).map(dimension=>[dimension,Array.from(U.unitsForDimension(dimension))]))]));
  assert.deepEqual(plain(catalog),backend);
});
test('output chart conversion retains gaps and never changes canonical arrays', () => {
  const column={dimension:'speed',canonical_unit:'m/s',values:[0,10,null,NaN,Infinity]};
  const before=column.values.slice();
  const displayed=displayColumn(column,U.presetUnitPreferences('imperial'));
  near(displayed[1],22.369362920544);assert.deepEqual(plain(displayed).slice(2),[null,null,null]);
  assert.deepEqual(column.values,before);
});
test('absolute chart zoom limits convert with units but percentage bounds stay put', () => {
  const zoom=[{startValue:0,endValue:10},{startValue:0,endValue:10,start:20,end:80}];
  const before=JSON.stringify(zoom);const result=convertZoomUnits(zoom,'m/s','km/h');
  assert.equal(result[0],zoom[0]);near(result[1].endValue,36);assert.equal(result[1].end,80);
  assert.equal(JSON.stringify(zoom),before);
});
test('a no-op text group preserves an available redo operation', () => {
  const h=new DraftHistory({length:.03302});h.setValue({length:.04});h.undo();h.beginGroup('length');
  h.setQuantity('length',editQuantity('1.3 in','length','in',.03302,{}));h.setQuantity('length',undefined);h.endGroup();
  assert.equal(h.getSnapshot().canUndo,false);assert.equal(h.getSnapshot().canRedo,true);
  h.redo();assert.equal(h.getSnapshot().value.length,.04);
});
const selectedFixture=path.resolve(root,'../test/fixtures/belt_selected.json');
if(process.env.CVT_UPDATE_BELT_FIXTURE)fs.writeFileSync(selectedFixture,JSON.stringify(withBeltPreservingPrimaryShaft(initial,belt(.02)),null,2)+'\n');
else assert.deepEqual(plain(withBeltPreservingPrimaryShaft(initial,belt(.02))),JSON.parse(fs.readFileSync(selectedFixture,'utf8')));
// A real front-end-produced document is consumed by the backend cross-layer test.
if(process.env.CVT_EDITOR_FIXTURE)fs.writeFileSync(process.env.CVT_EDITOR_FIXTURE,JSON.stringify(withBeltPreservingPrimaryShaft(initial,belt(.02))));
console.log(JSON.stringify({editorFoundationChecks:count}));
