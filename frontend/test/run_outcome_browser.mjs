// Real run/detail/history/Activity/playback UI. APIs and expensive renderers are
// deterministic adapters; playback controls and saved-time bounds are real.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { chromium } from 'playwright';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const source = path.join(frontend, 'src');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'cinder-run-outcomes-'));
const fixtures = `
const copy = value => structuredClone(value);
const selected = new URLSearchParams(location.search).get('case') ?? 'internal';
const category = {internal:'internal_error',numerical:'numerical_error',vehicle:'vehicle_stopped',
  model:'model_limit',running:'pending',success:'success',evicted:'success'}[selected];
const titles = {internal_error:'Simulation error',numerical_error:'Solver stopped early',
  vehicle_stopped:'Vehicle stopped before the finish',model_limit:'Model limit reached',
  pending:'Simulation running',success:'Run completed'};
const messages = {internal_error:'The simulation encountered an internal error. No input change has been identified.',
  numerical_error:'The numerical solver could not continue this simulation.',
  vehicle_stopped:'The vehicle stopped making forward progress before the end of the course.',
  model_limit:'The mechanism reached a contact condition that this version of CINDER does not model.',
  pending:'The simulation is running on the server.',success:'The simulation reached its requested finish condition.'};
const makeOutcome = (kind = category, extra = {}) => ({ category:kind,reason:kind==='model_limit'?'mechanism_contact_unsupported':kind,
  severity:kind==='success'?'success':['vehicle_stopped','model_limit'].includes(kind)?'warning':kind==='pending'?'info':'error',
  title:titles[kind],message:messages[kind],action:kind==='internal_error'?'Share this run ID with the maintainer.':null,
  has_data:kind!=='internal_error',partial:!['internal_error','success'].includes(kind),
  reached_time_s:kind==='internal_error'?null:1.25,reached_distance_m:kind==='internal_error'?null:6.5,
  support_run_id:'test-run',...extra });
const outcome = makeOutcome();
const run = {id:'test-run',name:'Outcome test run',author:'Test user',author_id:null,
  status:category==='pending'?'running':['success','vehicle_stopped'].includes(category)?'completed':'failed',
  has_result:outcome.has_data && selected!=='evicted',outcome,
  submitted_at:'2026-10-06T10:00:00Z',started_at:'2026-10-06T10:00:01Z',completed_at:'2026-10-06T10:00:02Z',
  cinder_package_version:'1.1.5',summary_scalars:{metrics:{completed:category==='success',duration_s:1.25,
    vehicle_distance_final_m:6.5,termination_reason:'running'}},
  error:['internal_error','numerical_error','model_limit'].includes(category)
    ? {code:'simulation_failed',message:'RuntimeError: private implementation detail'}:null,
  provenance:{},runtime_identity:{},cancel_requested_at:null,parent_run_id:null,queue_position:null};
const harness = window.harness = {run,makeOutcome,inspectCalls:0,resultCalls:0,activityCalls:0,reads:[],resultFailure:false,
  notices:location.pathname==='/activity'?[{id:'notice-1',run,created_at:run.completed_at}]:[]};
export const isActive = run => ['queued','running','validating'].includes(run.status);
export const message = error => error.message ?? String(error);
export const inspectRun = async () => {
  harness.inspectCalls++;
  return copy({run:harness.run,owned:true,references:[],metrics:[],warnings:[],transitions:[],
    availability:{full_result:harness.run.has_result,preview:harness.run.outcome.has_data,
      partial:harness.run.outcome.partial},termination_reason:'running',experiment_unavailable_reason:null});
};
export const getActivity = async () => {
  harness.activityCalls++;
  return copy({active:isActive(harness.run)?harness.run:null,unread:harness.notices,unread_count:harness.notices.length});
};
export const listRuns = async () => copy([harness.run]);
export const readNotice = async id => {harness.reads.push(id);harness.notices=harness.notices.filter(item=>item.id!==id);};
export const cancelRun = async () => harness.run;
export const rerun = async () => ({id:'new-run'});
export const renameRun = async () => harness.run;
export const getHistory = async () => copy({items:[{run:harness.run,references:[],metrics:[]}],total:1,offset:0,limit:24});
export const exportRun = async () => new Blob(['saved data']);
export const formatMetric = metric => String(metric.value);
export const getFrozenInput = async () => ({input_document_snapshot:{}});
export const getSimulationResult = async () => {
  harness.resultCalls++;
  if(harness.resultFailure) throw Error('The saved trajectory could not be downloaded. Try again.');
  if(!harness.run.has_result) throw Error('A missing artifact must not be requested.');
  return copy({run:harness.run,inputDocumentSnapshot:{},sceneGeometry:{},course:null,
    result:{metrics:{completed:harness.run.outcome.category==='success',duration_s:1.25,termination_reason:'running'},
      report_table:{axis_key:'time_s',row_count:3,columns:[
        {key:'time_s',label:'Time',canonical_unit:'s',dimension:'time',group:'state',values:[0,.5,1.25]},
        {key:'vehicle.distance',label:'Position',canonical_unit:'m',dimension:'length',group:'vehicle',values:[0,2,6.5]}
      ]}}});
};
`;
fs.writeFileSync(path.join(temporary, 'fixtures.ts'), fixtures);
const fixtureExport = `export * from ${JSON.stringify(path.join(temporary, 'fixtures.ts'))};`;
const adapters = new Map([
  ['features/experiments/api.ts', fixtureExport],
  ['features/results/api.ts', fixtureExport],
  ['api/client.ts', fixtureExport],
  ['contexts/AuthContext.tsx', 'export const useAuth=()=>({session:{user:{display_name:"Test user"}}});'],
  ['features/results/ResultChart.tsx', 'export const ResultChart=()=> <p>Saved chart preview</p>;'],
  ['components/scene3DViewer/Scene3DViewer.tsx', 'export const Scene3DViewer=()=> <p>Saved trajectory scene</p>;'],
  ['pages/playback/PlotWorkspace.tsx', 'export const PlotWorkspace=()=>null;'],
  ['pages/playback/CoursePlayback.tsx', 'export const CoursePlayback=()=>null;'],
]);
const entry = `
import React from 'react';import {createRoot} from 'react-dom/client';
import {MantineProvider} from '@mantine/core';import '@mantine/core/styles.css';
import {BrowserRouter,Routes,Route} from 'react-router-dom';
import {RunPage} from ${JSON.stringify(path.join(source, 'features/experiments/RunPage.tsx'))};
import {RunHistory} from ${JSON.stringify(path.join(source, 'features/results/RunHistory.tsx'))};
import {Playback} from ${JSON.stringify(path.join(source, 'pages/playback/Playback.tsx'))};
import {RunActivityProvider,RunActivityBanner,RunActivityButton} from ${JSON.stringify(path.join(source, 'features/experiments/RunActivity.tsx'))};
createRoot(document.getElementById('root')).render(<MantineProvider><BrowserRouter><RunActivityProvider>
  <Routes><Route path='/runs/:runId' element={<RunPage/>}/><Route path='/playback' element={<Playback/>}/>
    <Route path='/history' element={<RunHistory/>}/>
    <Route path='/activity' element={<><RunActivityBanner/><RunActivityButton/></>}/></Routes>
</RunActivityProvider></BrowserRouter></MantineProvider>);
`;
await build({
  stdin: { contents: entry, loader: 'tsx', resolveDir: frontend },
  outfile: path.join(temporary, 'app.js'), bundle: true, format: 'esm', jsx: 'automatic',
  nodePaths: [path.join(frontend, 'node_modules')],
  alias: Object.fromEntries(['components','styles','utils','api','contexts'].map(name=>['@'+name,path.join(source,name)])),
  plugins: [{ name:'outcome-adapters', setup(plugin) {
    plugin.onLoad({filter:/\.[jt]sx?$/}, args => {
      const contents = adapters.get(path.relative(source,args.path).split(path.sep).join('/'));
      return contents === undefined ? undefined : {contents,loader:'tsx'};
    });
    plugin.onLoad({filter:/\.scss$/}, () => ({loader:'js',contents:'export default new Proxy({}, {get:(_,name)=>String(name)});'}));
  }}],
});
const server = http.createServer((request,response) => {
  const file = request.url === '/app.js' ? 'app.js' : request.url === '/app.css' ? 'app.css' : null;
  response.setHeader('Content-Type',file?.endsWith('.js')?'text/javascript':file?'text/css':'text/html');
  response.end(file?fs.readFileSync(path.join(temporary,file)):
    '<!doctype html><html><head><link rel="stylesheet" href="/app.css"></head><body><div id="root"></div><script type="module" src="/app.js"></script></body></html>');
});
await new Promise((resolve,reject) => {server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
let browser;
let cases=0;
try {
  browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
  const page=await browser.newPage({viewport:{width:1440,height:1100}});
  page.setDefaultTimeout(15000);
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  const open=async(url)=>page.goto(`http://127.0.0.1:${server.address().port}${url}`);
  const pass=name=>{console.log('PASS',name);cases++;};
  const noRawError=async()=>assert.doesNotMatch(await page.locator('body').innerText(),/private implementation detail|RuntimeError/);

  await open('/runs/test-run?case=internal');
  await page.getByText('No simulation data was saved. Playback is unavailable.',{exact:true}).waitFor();
  assert.equal(await page.getByRole('link',{name:/Open .*playback/}).count(),0);
  assert.match(await page.getByRole('status').innerText(),/No input change has been identified/);
  await noRawError();
  pass('a failure before data explains the error without offering empty playback or raw exceptions');

  await open('/playback?run=test-run&case=internal');
  await page.getByText('No simulation data was saved. Playback is unavailable.',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window.harness.resultCalls),0);
  assert.equal(await page.getByRole('button',{name:'Play',exact:true}).count(),0);
  await page.getByRole('link',{name:'View run details',exact:true}).waitFor();
  pass('a direct playback URL without data retains the run diagnosis and does not request an absent artifact');

  await open('/runs/test-run?case=numerical');
  await page.getByRole('link',{name:'Open partial playback',exact:true}).waitFor();
  if (process.env.RUN_OUTCOME_SCREENSHOT)
    await page.screenshot({path:process.env.RUN_OUTCOME_SCREENSHOT,fullPage:true});
  await page.getByRole('link',{name:'Open partial playback',exact:true}).click();
  await page.getByRole('region',{name:'Playback controls'}).waitFor();
  await page.getByText('Solver stopped early',{exact:true}).waitFor();
  assert.match(await page.getByRole('status').innerText(),/1\.25 s.*6\.5 m/);
  assert.match(await page.getByRole('status').innerText(),/Partial result/);
  await page.getByRole('slider').press('End');
  await page.getByText('0:01:25 / 0:01:25',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window.harness.resultCalls),1);
  await noRawError();
  pass('a partial solver failure opens playback and the real playbar ends at the last saved sample');

  await open('/history?case=vehicle');
  await page.getByText('Course not completed',{exact:true}).waitFor();
  assert.equal(await page.getByText('Completed',{exact:true}).count(),0);
  await page.getByRole('link',{name:'View run',exact:true}).click();
  await page.getByText('Vehicle stopped before the finish',{exact:true}).waitFor();
  await page.getByRole('link',{name:'Open partial playback',exact:true}).waitFor();
  pass('a processed course stop keeps its vehicle outcome in history and run detail');

  await open('/runs/test-run?case=model');
  await page.getByText('Model limit',{exact:true}).waitFor();
  assert.match(await page.getByRole('status').innerText(),/does not model/);
  assert.equal(await page.getByText('Check configuration',{exact:true}).count(),0);
  await noRawError();
  pass('an unsupported contact condition is a model limit without blaming the setup');

  await open('/runs/test-run?case=running');
  await page.getByText('Computing',{exact:true}).waitFor();
  await page.evaluate(()=>{window.harness.run={...window.harness.run,status:'failed',has_result:true,
    outcome:window.harness.makeOutcome('model_limit')};});
  await page.getByText('Model limit reached',{exact:true}).waitFor();
  assert.equal(await page.getByText('Computing',{exact:true}).count(),0);
  await page.getByRole('link',{name:'Open partial playback',exact:true}).waitFor();
  pass('polling replaces running status with the terminal outcome and partial playback action');

  await open('/activity?case=model');
  await page.getByRole('status').waitFor();
  await page.waitForFunction(()=>window.harness.activityCalls>=3);
  assert.equal(await page.getByRole('status').count(),1);
  assert.match(await page.getByRole('status').innerText(),/Model limit.*does not model/s);
  await page.getByRole('button',{name:'Dismiss',exact:true}).click();
  await page.getByRole('status').waitFor({state:'hidden'});
  await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
  assert.deepEqual(await page.evaluate(()=>window.harness.reads),['notice-1']);
  assert.equal(await page.getByRole('status').count(),0);
  pass('repeated Activity polls keep one notice and dismiss it once');

  await open('/playback?run=test-run&case=evicted');
  await page.getByText('Full result unavailable',{exact:true}).waitFor();
  assert.match(await page.getByRole('alert').innerText(),/saved preview.*Full playback.*unavailable/s);
  assert.equal(await page.evaluate(()=>window.harness.resultCalls),0);
  pass('an evicted full result explains preview availability without attempting full playback');

  assert.deepEqual(errors,[],'No uncaught browser errors');
  console.log(JSON.stringify({runOutcomeBrowserScenarios:cases}));
} finally {
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
  fs.rmSync(temporary,{recursive:true,force:true});
}
