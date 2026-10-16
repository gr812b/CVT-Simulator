// Exercise the real page and WebGL scene with CINDER-generated frame data.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import * as sass from 'sass';
import { chromium } from 'playwright';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const artifacts = process.env.CINDER_BACKEND_ARTIFACTS ?? path.resolve(root, '../backend/generated');
const sample = JSON.parse(fs.readFileSync(path.join(artifacts, 'sliding_block_demo.json'), 'utf8'));
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'cinder-sliding-block-'));
const source = path.join(root, 'src');
let browser, server;
try {
  await build({
    stdin: { contents: `import React from 'react';import {createRoot} from 'react-dom/client';
      import {MantineProvider} from '@mantine/core';import '@mantine/core/styles.css';
      import {MemoryRouter} from 'react-router-dom';import {SlidingBlockDemo} from './src/pages/slidingBlock/SlidingBlockDemo';
      createRoot(document.getElementById('root')).render(<MantineProvider defaultColorScheme="dark"><MemoryRouter><SlidingBlockDemo/></MemoryRouter></MantineProvider>);`, resolveDir: root, loader: 'tsx' },
    outfile: path.join(temporary, 'app.js'), bundle: true, format: 'esm', jsx: 'automatic',
    nodePaths: [path.join(root, 'node_modules')],
    alias: Object.fromEntries(['components', 'api', 'utils', 'hooks', 'contexts', 'styles'].map(name => ['@' + name, path.join(source, name)])),
    plugins: [{ name: 'demo-fixture', setup(plugin) {
      plugin.onLoad({ filter: /AuthContext\.tsx$/ }, () => ({ loader: 'tsx', contents: 'export const useAuth=()=>({session:null,loading:false,signOut:async()=>{}});' }));
      plugin.onLoad({ filter: /api\/client\.ts$/ }, () => ({ loader: 'ts', contents: `export async function getSlidingBlockDemo(signal) {const r=await fetch('/sample.json',{signal});if(!r.ok)throw new Error('Unable to load sample');return r.json();}` }));
      plugin.onLoad({ filter: /\.module\.scss$/ }, args => ({ loader: 'local-css', contents: sass.compile(args.path).css }));
    } }],
  });
  let fail = true;
  server = http.createServer((request, response) => {
    if (request.url === '/sample.json') { response.setHeader('Content-Type', 'application/json');response.statusCode=fail?503:200;response.end(JSON.stringify(sample));return; }
    const file = request.url === '/app.js' ? 'app.js' : request.url === '/app.css' ? 'app.css' : null;
    response.setHeader('Content-Type', file?.endsWith('.js') ? 'text/javascript' : file ? 'text/css' : 'text/html');
    response.end(file ? fs.readFileSync(path.join(temporary, file)) : '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/app.css"></head><body><div id="root"></div><script type="module" src="/app.js"></script></body></html>');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'], ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.getByRole('alert').filter({ hasText: 'Sample unavailable' }).waitFor();
  fail = false; await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await page.getByTestId('closure-value').waitFor();
  await page.getByRole('alert').filter({ hasText: 'Face contact study' }).waitFor();
  await page.getByText('Pressure dependent', { exact: true }).waitFor();
  await page.getByTestId('moving-contact-span').waitFor();
  assert.equal(await page.getByTestId('moving-contact-span').getAttribute('stroke-width'), '5');
  await page.locator('[data-testid="sliding-3d"] canvas').waitFor();
  const slider = page.getByRole('slider', { name: 'Sheave closure', exact: true });
  await slider.press('End');
  await page.getByTestId('closure-value').filter({ hasText: '15.00' }).waitFor();
  assert.equal(Number(await page.getByTestId('section-block').getAttribute('data-radial')), sample.frames.at(-1).datum_m[0]);
  assert.equal(Number(await page.getByTestId('section-block').getAttribute('data-axial')), sample.frames.at(-1).datum_m[1]);
  await page.getByRole('switch', { name: 'Cutaway', exact: true }).uncheck();
  await page.getByRole('switch', { name: 'Cutaway', exact: true }).check();
  await page.getByRole('switch', { name: 'Contacts & normals' }).uncheck();
  assert.equal(await page.getByTestId('moving-contact-span').count(), 0);
  await page.getByRole('switch', { name: 'Contacts & normals' }).check();
  await page.getByTestId('moving-contact-span').waitFor();
  await page.getByRole('button', { name: 'Reset view' }).click();
  await page.getByRole('button', { name: 'Return to open' }).click();
  await page.getByTestId('closure-value').filter({ hasText: '0.00' }).waitFor();
  await page.getByRole('button', { name: 'Play stroke' }).click();
  await page.waitForFunction(() => Number(document.querySelector('[data-testid="section-block"]').getAttribute('data-axial')) > .0001);
  await page.getByRole('button', { name: 'Pause stroke' }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await slider.press('End');
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  assert.equal(await slider.getAttribute('aria-valuetext'), '15.00 millimetres');
  assert.deepEqual(errors, []);
  console.log('PASS sliding-block retry, WebGL, exact frames, keyboard closure, cutaway rebuild, contacts, reset, playback and mobile layout');
} finally {
  if (browser) await browser.close();
  if (server) await new Promise(resolve => server.close(resolve));
  fs.rmSync(temporary, { recursive: true, force: true });
}
