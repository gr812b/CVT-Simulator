// Real React/Mantine inputs, history and AuthProvider. Only the network/auth
// persistence is an adapter; this is not a live backend or CINDER acceptance run.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { chromium } from 'playwright';
const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'cinder-editor-foundation-'));
const source = path.join(frontend, 'src');
const adapters = new Map([
  ['api/transport.ts', `export class ApiClientError extends Error {
    constructor(status) { super('Test API failure'); this.status=status; }
  }
  export const SESSION_EXPIRED='test-session-expired'; export function setCsrfToken() {}`],
  ['api/auth.ts', `import {ApiClientError} from './transport';
    export const getSession=async()=>{
      await new Promise(resolve=>setTimeout(resolve,100));
      if(localStorage.getItem('test-signed-out')) throw new ApiClientError(401);
      return {user:{id:'test-user',display_name:'Test user',unit_preferences:JSON.parse(localStorage.getItem('test-unit-preferences')??'null')},
        account:{id:'test-account'},csrf_token:'test-csrf',expires_at:new Date(Date.now()+3600000).toISOString()};
    };
    export const updateUnitPreferences=async preferences=>{
      localStorage.setItem('test-unit-preferences',JSON.stringify(preferences));return getSession();
    };
    export const logout=async()=>{localStorage.setItem('test-signed-out','1');};`],
]);
const entry = `import React from 'react';import {createRoot} from 'react-dom/client';
import {MantineProvider} from '@mantine/core';import '@mantine/core/styles.css';
import {EditorFoundationFixture} from ${JSON.stringify(path.join(frontend,'test/fixtures/editorFoundation.tsx'))};
createRoot(document.getElementById('root')).render(<MantineProvider><EditorFoundationFixture/></MantineProvider>);`;
let browser, server;
let count = 0;
try {
  await build({stdin:{contents:entry,loader:'tsx',resolveDir:frontend},outfile:path.join(temporary,'app.js'),
    bundle:true,format:'esm',jsx:'automatic',nodePaths:[path.join(frontend,'node_modules')],
    alias:Object.fromEntries(['components','contexts','api','utils','styles'].map(name=>['@'+name,path.join(source,name)])),
    plugins:[{name:'auth-fixture',setup(plugin){plugin.onLoad({filter:/\.[jt]sx?$/},args=>{
      const contents=adapters.get(path.relative(source,args.path).split(path.sep).join('/'));
      return contents===undefined?undefined:{contents,loader:'tsx'};
    });}}],
  });
  server=http.createServer((request,response)=>{
    const file=request.url==='/app.js'?'app.js':request.url==='/app.css'?'app.css':null;
    response.setHeader('Content-Type',file?.endsWith('.js')?'text/javascript':file?'text/css':'text/html');
    response.end(file?fs.readFileSync(path.join(temporary,file)):
      '<!doctype html><html><head><link rel="stylesheet" href="/app.css"></head><body><div id="root"></div><script type="module" src="/app.js"></script></body></html>');
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
  const context=await browser.newContext();const page=await context.newPage();const errors=[];
  page.on('pageerror',error=>errors.push(error.message));page.setDefaultTimeout(10000);
  const url=`http://127.0.0.1:${server.address().port}`;await page.goto(url);
  const button=name=>page.getByRole('button',{name,exact:true});
  const length=page.getByLabel('Test length',{exact:true});
  const inertia=page.getByLabel('Test inertia',{exact:true});await length.waitFor();
  const state=async()=>JSON.parse(await page.getByTestId('state').innerText());
  const until=async predicate=>page.waitForFunction(`(${predicate})(JSON.parse(document.querySelector('[data-testid=state]').textContent))`);
  const pass=name=>{count++;console.log('PASS',name);};
  const original=(await state()).value.inertia;await inertia.focus();await inertia.blur();
  assert.equal((await state()).value.inertia,original);assert.equal((await state()).dirty,false);pass('untouched focus/blur preserves exact SI');
  await length.fill('broken');await length.blur();assert.equal(await length.inputValue(),'broken');
  await until('s=>s.invalid>0');assert.equal(await button('Save draft').isDisabled(),true);pass('invalid text survives blur and prevents save');
  await button('Toggle length visibility').click();assert.ok((await state()).invalid>0);
  await button('Toggle length visibility').click();assert.equal(await length.inputValue(),'broken');pass('hidden raw quantity survives remount');
  await button('Undo').click();await until('s=>s.invalid===0');assert.equal((await state()).dirty,false);
  await button('Redo').click();assert.equal(await length.inputValue(),'broken');pass('undo/redo restores invalid text and its value together');
  await button('Discard draft').click();await until('s=>s.invalid===0');
  await length.fill('33.02 mm');await length.blur();assert.equal((await state()).dirty,false);
  assert.equal((await state()).value.length,.03302);pass('equivalent typed units remain clean');
  await length.fill('1.5 in');await length.blur();await button('Toggle failed save').click();
  await button('Save draft').click();assert.equal((await state()).message,'Save failed');assert.equal((await state()).dirty,true);pass('failed save retains draft');
  await button('Toggle failed save').click();await button('Save draft').click();assert.equal((await state()).dirty,false);
  await button('Undo').click();assert.equal((await state()).value.length,.03302);assert.equal((await state()).dirty,true);
  await button('Redo').click();assert.equal((await state()).dirty,false);pass('saving retains history with a new clean baseline');
  await button('Change belt').click();assert.ok(Math.abs((await state()).shaft-.025)<1e-14);
  await button('Undo').click();assert.equal((await state()).value.cvt.belt.data.height_m,.015);
  await button('Redo').click();assert.equal((await state()).value.cvt.assembly.geometry.belt.height_m,.02);pass('compound belt edit undoes atomically');
  await page.getByTestId('keyboard-target').focus();await page.keyboard.press('Control+z');
  assert.equal((await state()).value.cvt.belt.data.height_m,.015);await page.keyboard.press('Control+Shift+z');
  assert.equal((await state()).value.cvt.belt.data.height_m,.02);pass('keyboard undo/redo outside inputs');
  await length.focus();await page.keyboard.press('Control+a');await page.keyboard.type('0.4 in',{delay:20});await page.keyboard.press('Control+z');
  assert.equal((await state()).value.cvt.belt.data.height_m,.02);pass('native text undo does not undo an unrelated form operation');
  await button('Discard draft').click();await length.fill('2');
  // A second page shares the authentication cookie/session fixture and broadcasts real events.
  const other=await context.newPage();other.on('pageerror',error=>errors.push(error.message));await other.goto(url);
  await other.getByLabel('Test length',{exact:true}).waitFor();
  await other.getByRole('button',{name:'SI preferences',exact:true}).click();await until("s=>s.preferences.hardware_length==='m'");
  assert.equal(await page.locator('body').getAttribute('data-signed-out'),null);
  assert.ok(Math.abs((await state()).value.length-.0508)<1e-14);assert.equal(await length.inputValue(),'2');pass('cross-tab preferences keep identity and in-progress text');
  await length.blur();assert.ok(Math.abs((await state()).value.length-.0508)<1e-14);assert.match(await length.inputValue(),/ m$/);pass('entry unit remains fixed until normalization');
  await button('Discard draft').click();const before=(await state()).value;
  await other.getByRole('button',{name:'Recommended preferences',exact:true}).click();await until("s=>s.preferences.hardware_length==='in'");
  assert.deepEqual((await state()).value,before);assert.equal((await state()).dirty,false);pass('unfocused display changes never alter the document');
  await other.getByRole('button',{name:'Sign out',exact:true}).click();await page.getByText('Signed out',{exact:true}).waitFor();pass('real sign-out still propagates');
  assert.deepEqual(errors,[]);console.log(JSON.stringify({actualReactMantineFoundationCases:count}));
} finally {
  await browser?.close();
  if(server?.listening) await new Promise(resolve=>server.close(resolve));
  fs.rmSync(temporary,{recursive:true,force:true});
}
