// Real React/Mantine interaction tests of ExperimentPage + TuneDialog.
// Persistence and unrelated editors are deterministic adapters; this is not a
// CINDER/whole-application acceptance test. Requires esbuild, Playwright and Chromium.
// Run from frontend: npm run test:browser
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { build } from 'esbuild';
import { chromium } from 'playwright';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'cinder-tune-selection-'));
const source = path.join(root, 'frontend/src');

const fixtures = `
const copy = value => structuredClone(value);
let revision = 1;
const item = (id, kind, name, cvt = null) => ({id,kind,name,revision_id:id+'-1',revision_number:1,
  owned:true,sample:false,archived:false,description:'',author:'Test author',cvt_revision_id:cvt,cvt_object_id:'cvt'});
const detail = (id, name, weight = .8, cvt = 'cvt-1') => ({
  item:item(id,'tunes',name,cvt),document:{kind:'tunes',name,notes:'',cvt_revision_id:cvt,values:{primary_mass:weight}}
});
const reference=detail('reference','Reference'), alternative=detail('alternative','Alternative',.9), other=detail('other','Other CVT tune',.7,'cvt-2');
reference.item.owned = !new URLSearchParams(location.search).has('public');
const defaultFor = cvt => cvt === 'cvt-1' ? tunes.reference : tunes.other;
const tunes = {reference, alternative, other};
const belt={name:'Shared belt',revision_id:'belt-1',data:{}};
const cvt = revision => ({name:revision==='cvt-1'?'CVT one':'CVT two',revision_id:revision,data:{belt,assembly:{}}});
const setup = id => ({item:item(id,'setups',id==='vehicle-a'?'Vehicle A':'Vehicle B'),document:{kind:'setups',name:id==='vehicle-a'?'Vehicle A':'Vehicle B',
  data:{vehicle:{mass_kg:225},engine:{name:'Engine',revision_id:'engine-1',data:{external_torque_Nm:10}},cvt:cvt('cvt-1')}}});
const setups = {'vehicle-a':setup('vehicle-a'),'vehicle-b':setup('vehicle-b')};
const scenario={item:{...item('road','scenarios','Flat road'),sample:true},document:{kind:'scenarios',name:'Flat road',notes:'',duration_s:5,stops:{mode:'timed'},road:{features:[]}}};
const harness = window.harness = {runs:[],previews:[],physicalSaves:[],tuneSaves:[],rejectSave:false,tunes,setups};
export const getExperimentMetadata = async () => ({});
export const getTuneSurface = async revision => copy({cvt_name:cvt(revision).name,cvt_revision_id:revision,cvt_object_id:'cvt',
  fields:[],default_tune:defaultFor(revision),template:defaultFor(revision).document});
export const listExperiments = async kind => copy(kind==='tunes'?Object.values(tunes).map(t=>t.item):[scenario.item]);
export const getExperiment = async id => copy(tunes[id]??scenario);
export const saveExperiment = async (document, previous, asNew) => {
  if(harness.rejectSave) {harness.rejectSave=false;throw Error('Full construction check rejected this draft.');}
  const id=asNew?'copy-'+(++revision):previous.item.id;
  const saved={item:{...item(id,'tunes',document.name,document.cvt_revision_id),revision_id:id+'-'+(++revision),revision_number:revision},document:copy(document)};
  tunes[id]=saved;harness.tuneSaves.push(copy(saved));return copy(saved);
};
export const previewExperiment = async body => {harness.previews.push(copy(body));return {validation:{is_valid:true,findings:[]}};};
export const submitExperiment = async body => {harness.runs.push(copy(body));return {id:'run-'+harness.runs.length};};
export const message = reason => reason.message??String(reason);
export const physicalMetadata = async () => ({cvt_fields:[]});
export const listPhysical = async kind => copy(kind==='setups'?Object.values(setups).map(s=>s.item):kind==='cvts'?
  [1,2].map(n=>({...item('cvt-'+n,'cvts','CVT '+(n===1?'one':'two')),revision_id:'cvt-'+n})):[]);
export const getPhysical = async (kind,id,revision) => kind==='setups'?copy(setups[id]):{
  item:{...item(id,kind,cvt(revision).name),revision_id:revision},document:{kind:'cvts',...cvt(revision)}};
export const physicalTemplate = async () => copy(setups['vehicle-a'].document);
export const validatePhysical = async () => ({validation:{is_valid:true,findings:[]}});
export const savePhysical = async (document, expected, id) => {
  const saved={item:{...item(id??'saved-vehicle','setups',document.name),revision_id:'saved-setup-'+(++revision)},document:copy(document)};
  setups[saved.item.id]=saved;harness.physicalSaves.push(copy(saved));return {detail:copy(saved),changed:true};
};
export const singularLabels = {cvts:'CVT',engines:'engine',belts:'belt'};
`;
fs.writeFileSync(path.join(temporary, 'fixtures.ts'), fixtures);
const adapters = new Map([
  ['features/experiments/api.ts', fixtures],
  ['features/physicalLibrary/api.ts', `export * from ${JSON.stringify(path.join(temporary, 'fixtures.ts'))};`],
  ['features/experiments/RunActivity.tsx', 'export const useRunActivity=()=>({activity:{active:null},refresh:async()=>{}});'],
  ['features/results/api.ts', 'export const getRunExperiment=async()=>null;'],
  ['features/experiments/LoadCaseEditor.tsx', 'export const LoadCaseEditor=()=>null;'],
  ['features/experiments/RoadPreview.tsx', 'export const RoadPreview=()=>null;'],
  ['features/experiments/ScenarioEditor.tsx', 'export const ScenarioEditor=()=>null;'],
  ['features/physicalLibrary/CvtEditor.tsx', 'export const CvtEditor=()=>null;'],
  ['features/physicalLibrary/PhysicalStatus.tsx', 'export const PhysicalStatus=()=>null;'],
  ['features/physicalLibrary/VehicleEditor.tsx', 'export const VehicleEditor=()=>null;'],
  ['features/experiments/PrimaryBoundaryEditor.tsx', 'export const PrimaryBoundaryEditor=({children})=><>{children}</>;'],
  ['components/form/EditorDisclosure.tsx', 'export const EditorDisclosure=({children})=><>{children}</>;'],
  ['features/physicalLibrary/EngineEditor.tsx', `import {TextInput} from '@mantine/core';
    export const EngineEditor=({value,onChange})=><TextInput label="Engine test setting" value={value.external_torque_Nm}
      onChange={event=>onChange({...value,external_torque_Nm:Number(event.currentTarget.value)})}/>;`],
  ['features/experiments/TuneEditor.tsx', `import {useEffect} from 'react';import {TextInput} from '@mantine/core';
    import {tuneInputKey} from './tunePreviewState';
    export function TuneEditor({value,onChange,onValidationChange}) {
      const inputKey=tuneInputKey(value);
      useEffect(()=>onValidationChange?.({inputKey,validation:{is_valid:true,findings:[]}}),[inputKey,onValidationChange]);
      return <><TextInput label="Test flyweight mass" value={value.values.primary_mass}
        onChange={event=>onChange({...value,values:{...value.values,primary_mass:Number(event.currentTarget.value)}})}/>
        <output data-testid="draft-mass">{value.values.primary_mass}</output></>;
    }`],
]);
// Both API import locations share a single fixture store, just as they would
// share server persistence. Duplicating this module would hide stale revisions.
adapters.set('features/experiments/api.ts', `export * from ${JSON.stringify(path.join(temporary, 'fixtures.ts'))};`);
if (process.env.RUN_BUILDER_SOURCE) {
  adapters.set('features/experiments/ExperimentPage.tsx', fs.readFileSync(process.env.RUN_BUILDER_SOURCE, 'utf8'));
}
if (process.env.TUNE_DIALOG_SOURCE) {
  adapters.set('features/experiments/TuneDialog.tsx', fs.readFileSync(process.env.TUNE_DIALOG_SOURCE, 'utf8'));
}
const entry = `
import React from 'react';import {createRoot} from 'react-dom/client';
import {MantineProvider} from '@mantine/core';import '@mantine/core/styles.css';
import {createBrowserRouter,RouterProvider} from 'react-router-dom';
import {ExperimentPage} from ${JSON.stringify(path.join(source, 'features/experiments/ExperimentPage.tsx'))};
const router=createBrowserRouter([{path:'/input',element:<ExperimentPage/>},{path:'/runs/:id',element:<p>Run saved</p>}]);
createRoot(document.getElementById('root')).render(<MantineProvider><RouterProvider router={router}/></MantineProvider>);
`;
await build({
  stdin: { contents: entry, loader: 'tsx', resolveDir: path.join(root, 'frontend') },
  outfile: path.join(temporary, 'app.js'), bundle: true, format: 'esm', jsx: 'automatic',
  nodePaths: [path.join(root, 'frontend/node_modules')],
  alias: Object.fromEntries(['components', 'styles', 'utils', 'api', 'contexts'].map(name => ['@'+name,path.join(source,name)])),
  plugins: [{ name:'test-adapters', setup(plugin) {
    plugin.onLoad({filter:/\.[jt]sx?$/}, args => {
      const replacement=adapters.get(path.relative(source,args.path).split(path.sep).join('/'));
      return replacement===undefined?undefined:{contents:replacement,loader:'tsx'};
    });
  }}],
});
const server=http.createServer((request,response)=>{
  const file=request.url==='/app.js'?'app.js':request.url==='/app.css'?'app.css':null;
  response.setHeader('Content-Type',file?.endsWith('.js')?'text/javascript':file?'text/css':'text/html');
  response.end(file?fs.readFileSync(path.join(temporary,file)):
    '<!doctype html><html><head><link rel="stylesheet" href="/app.css"></head><body><div id="root"></div><script type="module" src="/app.js"></script></body></html>');
});
await new Promise((resolve,reject)=>{
  server.once('error',reject);
  server.listen(Number(process.env.TUNE_TEST_PORT??0),'127.0.0.1',resolve);
});
let browser;
let page;
let cases=0;
try {
  browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
  page=await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('dialog',dialog=>dialog.accept());
  page.setDefaultTimeout(15000);
  const button=name=>page.getByRole('button',{name,exact:true});
  const choose=async(label,name)=>{
    await page.getByRole('combobox',{name:label,exact:true}).click();
    await page.getByRole('option',{name,exact:true}).click();
  };
  const open=async query=>{
    await page.goto(`http://127.0.0.1:${server.address().port}/input?setup=vehicle-a${query??''}`);
    await page.getByRole('combobox',{name:'Saved vehicle setup',exact:true}).waitFor();
    await button('Next').click();await button('Next').click();
    await page.getByRole('combobox',{name:'CVT tune',exact:true}).waitFor();
  };
  const edit=async (mass,name)=>{
    await button('Adjust tune').click();
    await page.getByLabel('Test flyweight mass',{exact:true}).fill(String(mass));
    await page.getByLabel('Test flyweight mass',{exact:true}).blur();
    await page.getByTestId('draft-mass').filter({hasText:String(mass)}).waitFor();
    if(name)await page.getByLabel(/^Tune name/).fill(name);
  };
  const save=async()=>{
    await button('Save tune').click();
    await page.getByRole('dialog').waitFor({state:'hidden'});
    return page.evaluate(()=>window.harness.tuneSaves.at(-1));
  };
  const submit=async expected=>{
    await button('Next').click();
    await page.getByLabel('Engine test setting',{exact:true}).fill('12');
    await button('Save setup & choose load case').click();
    await button('Review simulation').click();
    await page.getByLabel(/^Run name/).fill('Saved tune regression');
    await button('Run simulation').click();
    await page.getByText('Run saved',{exact:true}).waitFor();
    const state=await page.evaluate(()=>window.harness);
    assert.equal(state.physicalSaves.length,1,'The setup must actually have been saved.');
    assert.equal(state.runs.at(-1).setup_revision_id,state.physicalSaves[0].item.revision_id);
    assert.equal(state.runs.at(-1).tune_revision_id,expected.item.revision_id);
    assert.deepEqual(state.runs.at(-1).tune_values,expected.document.values);
    assert.equal(state.previews.at(-1).tune_revision_id,expected.item.revision_id);
    assert.deepEqual(state.previews.at(-1).tune_values,expected.document.values);
  };

  await open();await edit(1.1);const revised=await save();
  assert.equal(revised.document.values.primary_mass,1.1);
  await choose('CVT tune','Alternative');await choose('CVT tune','Reference · Default');
  await submit(revised);
  console.log('PASS saving the default tune replaces its cached revision through picker, setup save, preview and run submission');cases++;

  await open();await choose('CVT tune','Alternative');await edit(1.2);const selected=await save();
  assert.equal(selected.document.values.primary_mass,1.2);
  await button('Back').click();await button('Back').click();
  await choose('Saved vehicle setup','Vehicle B');
  await button('Next').click();await button('Next').click();
  assert.equal(await page.getByRole('combobox',{name:'CVT tune',exact:true}).inputValue(),'Alternative');
  await submit(selected);
  console.log('PASS changing vehicle with the same CVT keeps the just-saved tune and submits its exact revision');cases++;

  await open('&public=1');await edit(.72,'My saved tune');const copied=await save();
  assert.notEqual(copied.item.id,'reference');
  assert.equal(copied.document.name,'My saved tune');
  assert.equal(copied.document.values.primary_mass,.72);
  await button('Back').click();await button('Back').click();
  await choose('Saved vehicle setup','Vehicle B');await button('Next').click();await button('Next').click();
  assert.equal(await page.getByRole('combobox',{name:'CVT tune',exact:true}).inputValue(),'My saved tune');
  await submit(copied);
  console.log('PASS copying a public tune selects and submits the newly saved ID, revision and edited values');cases++;

  await open('&tune=reference');await choose('CVT tune','Alternative');await edit(1.3);const linked=await save();
  assert.equal(linked.document.values.primary_mass,1.3);
  await button('Back').click();await button('Back').click();
  await choose('Saved vehicle setup','Vehicle B');await button('Next').click();await button('Next').click();
  await submit(linked);
  console.log('PASS a catalog-linked tune cannot replace a later explicit saved selection');cases++;

  await open();await edit(1.4);await save();
  await button('Back').click();await choose('Saved CVT','CVT two');await button('Next').click();
  assert.equal(await page.getByRole('combobox',{name:'CVT tune',exact:true}).inputValue(),'Other CVT tune · Default');
  const other=await page.evaluate(()=>window.harness.tunes.other);
  // The CVT change saves the setup before entering Tune; this case only needs
  // to verify that an incompatible old tune is not retained.
  await button('Next').click();await button('Next').click();await button('Review simulation').click();
  await page.getByLabel(/^Run name/).fill('Changed CVT');await button('Run simulation').click();
  await page.getByText('Run saved',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window.harness.runs.at(-1).tune_revision_id),other.item.revision_id);
  console.log('PASS intentionally changing CVT uses a compatible tune');cases++;

  await open('&tune=reference');await button('Back').click();
  await choose('Saved CVT','CVT two');await button('Next').click();
  await page.evaluate(()=>{
    const vehicle=window.harness.setups['vehicle-b'];
    vehicle.document.data.cvt={...vehicle.document.data.cvt,revision_id:'cvt-2',name:'CVT two'};
  });
  await button('Back').click();await button('Back').click();
  await choose('Saved vehicle setup','Vehicle B');await button('Next').click();
  assert.equal(await page.getByRole('combobox',{name:'Saved CVT',exact:true}).inputValue(),'CVT two');
  await button('Next').click();
  assert.equal(await page.getByRole('combobox',{name:'CVT tune',exact:true}).inputValue(),'Other CVT tune · Default');
  console.log('PASS changing CVT clears an incompatible catalog tune before later vehicle selections');cases++;

  await open();await edit(1.5);await page.evaluate(()=>{window.harness.rejectSave=true;});
  await button('Save tune').click();
  await page.getByText('Full construction check rejected this draft.',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window.harness.tuneSaves.length),0);
  await button('Cancel').click();await button('Discard changes').click();
  await submit(await page.evaluate(()=>window.harness.tunes.reference));
  console.log('PASS rejected tune save and discarded edits retain the last accepted tune');cases++;

  await open();await edit(1.6);await button('Use for this run only').click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  const unsaved=await page.evaluate(()=>({ ...window.harness.tunes.reference,
    document:{...window.harness.tunes.reference.document,values:{primary_mass:1.6}}}));
  await submit(unsaved);
  assert.equal(await page.evaluate(()=>window.harness.tuneSaves.length),0);
  console.log('PASS run-only tune edits survive setup saving without saving a library tune');cases++;
  assert.deepEqual(errors,[],'Unexpected React/browser runtime errors');
  console.log(`PASS ${cases} actual React/Mantine run-builder scenarios (API/editor adapters)`);
} catch (error) {
  if (page) console.error((await page.locator('body').innerText()).slice(0,6000));
  throw error;
} finally {
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
  fs.rmSync(temporary,{recursive:true,force:true});
}
