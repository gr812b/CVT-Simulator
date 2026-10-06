// Pure helpers and JSX adapter checks. This is NOT a React/browser/app build.
// Run from the repo: node tools/tune_editor_checks/frontend_checks.mjs
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const requireFromProject = createRequire(path.join(root, 'frontend/package.json'));
const ts = process.env.TYPESCRIPT_PATH ? createRequire(import.meta.url)(process.env.TYPESCRIPT_PATH) : requireFromProject('typescript');
const files = [
  'frontend/src/components/scene3DViewer/GeometryScene.tsx',
  'frontend/src/components/scene3DViewer/InspectionOverlay.tsx',
  'frontend/src/components/scene3DViewer/inspectionFrame.ts',
  'frontend/src/features/experiments/AngleProfileEditor.tsx',
  'frontend/src/features/experiments/ProfileSketch.tsx',
  'frontend/src/features/experiments/TuneDialog.tsx',
  'frontend/src/features/experiments/TuneEditor.tsx',
  'frontend/src/features/experiments/profileStages.ts',
  'frontend/src/features/experiments/tunePreviewState.ts',
  'frontend/src/pages/home/Home.tsx',
  'frontend/src/config/projectLinks.ts',
];
for (const file of files) {
  const parsed = ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
    fileName: file, reportDiagnostics: true,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX, strict: true },
  });
  assert.equal(parsed.diagnostics?.filter(d => d.category === ts.DiagnosticCategory.Error).length, 0, file);
}
const jsx = (type, props) => ({ type, props: props ?? {} });
let hookState = [], hookIndex = 0;
const react = {
  useState(initial) {
    const index = hookIndex++;
    if (!(index in hookState)) hookState[index] = typeof initial === 'function' ? initial() : initial;
    return [hookState[index], next => { hookState[index] = typeof next === 'function' ? next(hookState[index]) : next; }];
  },
  useEffect() {},
  useRef(initial) { return { current: initial }; },
  lazy() { return 'LazyPreview'; },
  Suspense: 'Suspense',
};
const cache = new Map();
function load(relative, extra = {}) {
  const filename = path.resolve(root, relative);
  if (cache.has(filename)) return cache.get(filename);
  const text = fs.readFileSync(filename, 'utf8');
  const output = ts.transpileModule(text, { fileName: filename, compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const context = { exports: {}, structuredClone, console, Set, URLSearchParams, ...extra };
  context.require = name => {
    if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx, Fragment: 'Fragment' };
    if (name === 'react') return react;
    if (name === '@mantine/core') return new Proxy({}, { get: (_, name) => name });
    if (name.includes('quantityInput/validation')) return { QuantityValidationContext: { Provider: 'ValidationProvider' } };
    if (name.includes('button/ActionButton')) return { ActionButton: 'Button' };
    if (name.includes('quantityInput/QuantityInput')) return { QuantityInput: 'QuantityInput' };
    if (name.includes('modal/Modal')) return { Modal: 'Modal' };
    if (name.includes('form/FormError')) return { FormError: 'FormError' };
    if (name.endsWith('styles/theme')) return { overlayLayers: { modalDropdown: 200 } };
    if (name === './TuneEditor') return { TuneEditor: 'TuneEditor' };
    if (name === './api') return { saveExperiment: async () => { saves++; return {}; }, message: String };
    if (name === './mechanisms' || name === './sceneSpec') return {};
    if (name === '@contexts/AuthContext') return { useAuth: () => ({ session: null }) };
    if (name === 'react-router-dom') return { Link: 'Link' };
    if (name === '@tabler/icons-react') return new Proxy({}, { get: (_, name) => name });
    if (name === '@components/appShell/Brand') return { Brand: 'Brand' };
    if (name === '@components/appShell/PublicHeader') return { PublicHeader: 'PublicHeader' };
    if (name.endsWith('.module.scss')) return { default: new Proxy({}, { get: (_, name) => name }) };
    if (name === 'three') return {}; // Basis constants tested independently; no WebGL claim.
    if (name.startsWith('.')) {
      const candidate = path.resolve(path.dirname(filename), name);
      return load([candidate+'.ts', candidate+'.tsx'].find(fs.existsSync));
    }
    throw Error(`Unexpected runtime dependency in a focused test: ${name}`);
  };
  vm.runInNewContext(output, context, { filename });
  cache.set(filename, context.exports);
  return context.exports;
}
const prefix = 'frontend/src/features/experiments/';
const stages = load(prefix + 'profileStages.ts');
const gate = load(prefix + 'tunePreviewState.ts');
let count = 0, saves = 0;
const angle = degrees => degrees * Math.PI / 180;
function test(name, fn) { fn(); count++; console.log('PASS', name); }
function near(a, b) { assert.ok(Math.abs(a-b) < 1e-10, `${a} != ${b}`); }
const tune = { kind: 'tunes', name: 'Test', cvt_revision_id: 'r1', values: { primary_ramp_axial_offset: -.02 } };
const check = (value, valid=true) => ({ inputKey: gate.tuneInputKey(value), validation: { is_valid: valid, findings: valid ? [] : [{ severity:'error', message:'No contact at 12 mm.' }] } });

test('no check means disabled, not optimistic approval', () => assert.ok(gate.tuneGeometryBlocker(tune, null)));
test('completed valid current check enables actions', () => assert.equal(gate.tuneGeometryBlocker(tune, check(tune)), undefined));
test('a changed ramp offset immediately invalidates old approval', () => {
  const next = { ...tune, values: { primary_ramp_axial_offset: -.04 } };
  assert.equal(gate.tuneGeometryBlocker(next, check(tune)), 'Updating contact preview…');
});
test('a changed CVT revision invalidates old approval', () => assert.ok(gate.tuneGeometryBlocker({ ...tune, cvt_revision_id: 'r2' }, check(tune))));
test('changing name/description does not need a geometry recomputation', () => {
  assert.equal(gate.tuneGeometryBlocker({ ...tune, name: 'Renamed', notes: 'Notes' }, check(tune)), undefined);
});
test('a partial contact trace cannot enable actions', () => assert.match(gate.tuneGeometryBlocker(tune, check(tune, false)), /No contact/));
test('missing validation from an old backend fails closed', () => assert.ok(gate.tuneGeometryBlocker(tune, { inputKey: gate.tuneInputKey(tune) })));
test('network/preview failure overrides a prior valid check', () => assert.ok(gate.tuneGeometryBlocker(tune, { ...check(tune), error:'Network error' })));
test('an error finding blocks even an inconsistent positive status', () => {
  const result = check(tune); result.validation.findings.push({ severity:'error', message:'Construction failed' });
  assert.equal(gate.tuneGeometryBlocker(tune, result), 'Construction failed');
});
test('warnings are not treated as construction errors', () => {
  const result = check(tune); result.validation.findings.push({ severity:'warning', message:'Warning' });
  assert.equal(gate.tuneGeometryBlocker(tune, result), undefined);
});
const custom = { kind:'piecewise_ramp', segments:[{ kind:'circular_segment', length_m:.04, angle_start_rad:angle(30), angle_end_rad:angle(50), quadrant:1 }] };
test('all primary profiles have angle controls without an opening-time rewrite', () => {
  const before = JSON.stringify(custom), display = stages.primaryAngleStages(custom);
  near(display.start_angle_rad, angle(30)); near(display.stages[0].angle_rad, angle(50));
  near(display.stages[0].end_m, .04); assert.equal(JSON.stringify(custom), before);
});
test('first actual primary angle edit produces shared smooth joins', () => {
  const edited = stages.primaryAngleStages(custom); edited.stages[0].angle_rad = angle(55);
  const saved = stages.writeAngleStages(edited);
  assert.equal(saved.segments[0].kind, 'c3_transition_segment');
  near(Math.atan(saved.segments[0].slope_end), angle(55));
  assert.equal(saved.segments[0].curvature_end_per_m, 0);
});
test('existing custom C3 curvature is retained until a profile edit', () => {
  const profile = stages.writeAngleStages(stages.primaryAngleStages(custom));
  profile.segments[0].curvature_start_per_m = 4;
  const before = JSON.stringify(profile); stages.primaryAngleStages(profile);
  assert.equal(JSON.stringify(profile), before);
});
test('10-degree helix convention remains unchanged', () => {
  near(stages.MIN_HELIX_ANGLE, angle(10)); near(stages.storedAngle(angle(10),true), angle(80));
});
test('secondary final stage angle still occurs at 100% opening', () => {
  const profile = stages.constantProfile(.11,angle(40));
  const value = stages.readTravelStages(profile,[.01,.04]); value.stages[0].angle_rad=angle(60);
  const result = stages.writeTravelStages(value,[.01,.04],.11);
  near(stages.readTravelStages(result,[.01,.04]).stages.at(-1).end_m,.04);
  near(result.segments.at(-1).angle_rad,angle(60));
});
function walk(node, fn) {
  if (Array.isArray(node)) { node.forEach(n=>walk(n,fn)); return; }
  if (!node || typeof node !== 'object') return;
  fn(node); walk(node.props?.children, fn);
}
function find(node, predicate) { let result; walk(node, entry=> { if (!result && predicate(entry)) result=entry; }); return result; }
function text(node) {
  if (Array.isArray(node)) return node.map(text).join(' ');
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node !== 'object') return String(node);
  return text(node.props?.children);
}
function button(tree, name) { return find(tree, node => node.type==='Button' && text(node)===name); }
const { AngleProfileEditor } = load(prefix+'AngleProfileEditor.tsx');
test('primary custom profile exposes stage inputs with no conversion button', () => {
  hookState=[]; hookIndex=0; let calls=0;
  const tree=AngleProfileEditor({field:{angle_convention:'profile'}, value:custom, onChange:()=>calls++, readOnly:false});
  assert.ok(find(tree, n=>n.type==='QuantityInput' && n.props.label==='Stage 1 end angle'));
  assert.equal(button(tree,'Edit with angle stages'),undefined);
  assert.equal(button(tree,'Replace shape'),undefined); assert.equal(calls,0);
});
test('primary constant-angle action is direct inside the draft editor', () => {
  hookState=[]; hookIndex=0; let changed;
  const tree=AngleProfileEditor({field:{angle_convention:'profile'}, value:custom, onChange:n=>changed=n, readOnly:false});
  button(tree,'Use constant angle').props.onClick();
  assert.equal(changed.segments.length,1); assert.equal(changed.segments[0].kind,'linear_segment');
});
const { ProfileSketch } = load(prefix+'ProfileSketch.tsx');
const trace={coordinates_m:[0,.01,.02],values_m:[0,100,300],slope_angles_rad:[.1,.4,.2],used_start_m:0,used_end_m:.02};
const plotProps={trace,profile:stages.constantProfile(.02,.1), selected:0,onSelect:()=>{},contact:.01,helix:false};
test('primary plot uses evaluated angle, not duplicated radial shape', () => {
  const tree=ProfileSketch(plotProps);
  const other=ProfileSketch({...plotProps,trace:{...trace,values_m:[10000,-500,0]}});
  assert.equal(find(tree,n=>n.type==='polyline').props.points,find(other,n=>n.type==='polyline').props.points);
  assert.match(text(tree),/Ramp angle/); assert.doesNotMatch(text(tree),/Radial rise/);
});
test('angle plot retains keyboard-selectable stages and current contact marker', () => {
  let selected=-1; const tree=ProfileSketch({...plotProps,onSelect:i=>selected=i});
  const stage=find(tree,n=>n.type==='g' && n.props.role==='button');
  stage.props.onKeyDown({key:'Enter',preventDefault(){}}); assert.equal(selected,0);
  assert.ok(find(tree,n=>n.type==='line' && n.props.strokeDasharray==='4 3'));
});
const { TuneDialog } = load(prefix+'TuneDialog.tsx');
test('dialog actions stay disabled across edit, late reply, failure and repair', () => {
  hookState=[]; let uses=0;
  const props={surface:{template:tune,cvt_name:'CVT'},initial:tune,mode:'edit',onClose(){},onSaved(){},onUse(){uses++;}};
  const render=()=>{hookIndex=0;return TuneDialog(props);};
  let tree=render(); assert.ok(button(tree,'Save tune').props.disabledReason);
  let editor=find(tree,n=>n.type==='TuneEditor'); editor.props.onValidationChange(check(tune));
  tree=render(); assert.equal(button(tree,'Save tune').props.disabledReason,undefined);
  const changed={...tune,values:{primary_ramp_axial_offset:-.06}};
  editor=find(tree,n=>n.type==='TuneEditor'); editor.props.onChange(changed);
  tree=render(); assert.ok(button(tree,'Save tune').props.disabledReason);
  button(tree,'Use for this run only').props.onClick(); assert.equal(uses,0);
  editor=find(tree,n=>n.type==='TuneEditor'); editor.props.onValidationChange(check(tune));
  tree=render(); assert.ok(button(tree,'Save tune').props.disabledReason);
  editor=find(tree,n=>n.type==='TuneEditor'); editor.props.onValidationChange(check(changed,false));
  tree=render(); assert.match(button(tree,'Save tune').props.disabledReason,/No contact/);
  editor=find(tree,n=>n.type==='TuneEditor'); editor.props.onChange(tune);
  tree=render(); assert.ok(button(tree,'Save tune').props.disabledReason);
  editor=find(tree,n=>n.type==='TuneEditor'); editor.props.onValidationChange(check(tune));
  tree=render(); assert.equal(button(tree,'Save tune').props.disabledReason,undefined);
  button(tree,'Use for this run only').props.onClick(); assert.equal(uses,1); assert.equal(saves,0);
});
test('an invalid numeric text draft disables both actions despite valid geometry', () => {
  hookState=[]; hookIndex=0;
  const props={surface:{template:tune},initial:tune,mode:'edit',onClose(){},onSaved(){},onUse(){}};
  let tree=TuneDialog(props); find(tree,n=>n.type==='TuneEditor').props.onValidationChange(check(tune));
  find(tree,n=>n.type==='ValidationProvider').props.value(new Set(['offset-field']));
  hookIndex=0; tree=TuneDialog(props);
  assert.match(button(tree,'Save tune').props.disabledReason,/highlighted/);
  assert.match(button(tree,'Use for this run only').props.disabledReason,/highlighted/);
});
const basis=load('frontend/src/components/scene3DViewer/inspectionFrame.ts').inspectionBases;
const multiply=(matrix,v)=>[0,1,2].map(row=>matrix[row*4]*v[0]+matrix[row*4+1]*v[1]+matrix[row*4+2]*v[2]);
test('primary profile plane is face-on, radial up and positive axial right', () => {
  assert.deepEqual(multiply(basis.primary,[1,0,0]),[0,1,0]);
  assert.deepEqual(multiply(basis.primary,[0,0,-1]),[1,0,0]);
  assert.deepEqual(multiply(basis.primary,[0,1,0]),[0,0,-1]);
});
test('secondary shaft is Y-up and the first radial station faces the viewer', () => {
  assert.deepEqual(multiply(basis.secondary,[0,0,1]),[0,1,0]);
  assert.deepEqual(multiply(basis.secondary,[1,0,0]),[0,0,1]);
});
test('inspection rotations are proper rigid rotations, not mirror images', () => {
  for(const matrix of Object.values(basis)) {
    const a=multiply(matrix,[1,0,0]),b=multiply(matrix,[0,1,0]),c=multiply(matrix,[0,0,1]);
    const cross=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
    cross.forEach((x,i)=>near(x,c[i]));
  }
});
test('inspection basis keeps a fixed-length tuple for Matrix4.set', () => {
  // A union of differently inferred literal tuples transpiles but fails tsc's
  // fixed-arity spread check. Exercise that signature, not a fake full build.
  const source = ts.createSourceFile('inspectionFrame.ts', fs.readFileSync(path.join(root,
    'frontend/src/components/scene3DViewer/inspectionFrame.ts'), 'utf8'), ts.ScriptTarget.ES2022, true);
  const basisDeclaration = source.statements.find(statement => ts.isVariableStatement(statement)
    && statement.declarationList.declarations.some(declaration => declaration.name.getText(source) === 'inspectionBases'));
  assert.ok(basisDeclaration);
  const signature = Array.from({ length:16 }, (_,i) => `n${i}:number`).join(',');
  const content = `declare class Matrix4 { set(${signature}): this; }
    type InspectionMount = 'primary' | 'secondary';
    ${basisDeclaration.getText(source)}
    declare const mount: InspectionMount;
    new Matrix4().set(...inspectionBases[mount]);`;
  const filename = path.join(root, '__inspection_signature_check__.ts');
  const options = { strict:true, noEmit:true, target:ts.ScriptTarget.ES2022 };
  const host = ts.createCompilerHost(options), read = host.readFile.bind(host), get = host.getSourceFile.bind(host);
  host.readFile = file => file === filename ? content : read(file);
  host.getSourceFile = (file, languageVersion, ...rest) => file === filename
    ? ts.createSourceFile(file, content, languageVersion, true) : get(file, languageVersion, ...rest);
  const errors = ts.getPreEmitDiagnostics(ts.createProgram([filename], options, host));
  assert.equal(errors.length, 0, errors.map(diagnostic => ts.flattenDiagnosticMessageText(diagnostic.messageText, '\n')).join('\n'));
});

const { InspectionOverlay } = load('frontend/src/components/scene3DViewer/InspectionOverlay.tsx');
const overlay = InspectionOverlay({ controller: {}, mount: 'primary', geometry: {}, shift: 0 });
test('orientation triad is compact, transparent and anchored to the bottom-right edge', () => {
  const svg = find(overlay, node => node.type === 'svg' && node.props['aria-label'].includes('orientation'));
  assert.ok(svg);
  assert.equal(svg.props.style.right, 0); assert.equal(svg.props.style.bottom, 0);
  assert.equal(svg.props.style.left, undefined);
  assert.ok(svg.props.style.width <= 128); assert.ok(svg.props.style.height <= 92);
  assert.equal(svg.props.style.background, undefined); assert.equal(svg.props.style.borderRadius, undefined);
  assert.equal(svg.props.style.pointerEvents, 'none');
});
test('named mechanism reference points remain in their separate pointer-transparent overlay', () => {
  const markers = find(overlay, node => node.type === 'svg' && node.props['aria-label'] === 'Mechanism reference points');
  assert.ok(markers); assert.equal(markers.props.style.inset, 0);
  assert.equal(markers.props.style.pointerEvents, 'none');
  assert.match(text(markers), /Pivot/); assert.match(text(markers), /Ramp start/);
});
const { Home } = load('frontend/src/pages/home/Home.tsx');
const homepage = Home();
const about = find(homepage, node => node.props?.['aria-labelledby'] === 'author-title');
const paragraphs = [
  'This website is still a work in progress, and most of the interface was built with AI, so there are almost certainly some bugs. The CVT model itself is the part I’ve spent much more time on, and the full derivation, assumptions, and checks are in the paper.',
  'Experimental validation is still to come, so if you have access to a CVT dyno, test data, or anything else that could be useful, definitely hit me up below.',
  'Hopefully this makes the model a little easier to explore and CVTs a little less of a black box. Everything is free to use, and the source is on GitHub.',
  'If you have questions, find something broken, want to talk about the paper, or just have thoughts on the project, reach out.',
];
test('About this project contains all four supplied paragraphs verbatim', () => {
  assert.ok(about); assert.equal(text(find(about, node => node.props?.id === 'author-title')), 'About this project');
  const actual = about.props.children.filter(node => node?.type === 'Text' && node.props.c === 'dimmed').map(text);
  assert.equal(JSON.stringify(actual), JSON.stringify(paragraphs));
  assert.doesNotMatch(text(about), /A note from me|4\.9|Hey, I’m Kai/);
});
test('project contact area displays the requested email and Discord handle', () => {
  const contact = find(about, node => node.props?.['aria-label'] === 'Contact Kai');
  assert.ok(contact); assert.match(text(contact), /kai@kaiarseneau\.dev/);
  assert.match(text(contact).replace(/\s+/g, ' '), /Discord: Gr812b/);
  assert.equal(find(contact, node => node.type === 'Anchor').props.href, 'mailto:kai@kaiarseneau.dev');
  // A username is not a Discord user-ID URL: do not invent one.
  assert.equal(find(contact, node => /discord/.test(node.props?.href ?? '')), undefined);
});
test('the model-paper, GitHub and demo links remain present', () => {
  assert.ok(find(homepage, node => node.props?.href === 'https://doi.org/10.31224/8419'));
  assert.ok(find(homepage, node => node.props?.href === 'https://github.com/gr812b/CVT-Simulator'));
  assert.ok(find(homepage, node => node.props?.to === '/demo'));
});

console.log(JSON.stringify({ syntaxFiles:files.length, helperAndJsxAdapterTests:count, actualReactBrowserAndAppBuild:'NOT RUN' },null,2));
