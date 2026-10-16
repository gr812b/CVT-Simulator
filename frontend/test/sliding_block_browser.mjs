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
const artifacts =
  process.env.CINDER_BACKEND_ARTIFACTS ??
  path.resolve(root, '../backend/generated');
const sample = JSON.parse(
  fs.readFileSync(path.join(artifacts, 'sliding_block_demo.json'), 'utf8')
);
const cases = JSON.parse(
  fs.readFileSync(path.join(artifacts, 'sliding_block_demo_cases.json'), 'utf8')
);
const temporary = fs.mkdtempSync(
  path.join(os.tmpdir(), 'cinder-sliding-block-')
);
const source = path.join(root, 'src');
let browser, server;
try {
  await build({
    stdin: {
      contents: `import React from 'react';import {createRoot} from 'react-dom/client';
      import {MantineProvider} from '@mantine/core';import '@mantine/core/styles.css';
      import {MemoryRouter} from 'react-router-dom';import {SlidingBlockDemo} from './src/pages/slidingBlock/SlidingBlockDemo';
      createRoot(document.getElementById('root')).render(<MantineProvider defaultColorScheme="dark"><MemoryRouter><SlidingBlockDemo/></MemoryRouter></MantineProvider>);`,
      resolveDir: root,
      loader: 'tsx',
    },
    outfile: path.join(temporary, 'app.js'),
    bundle: true,
    format: 'esm',
    jsx: 'automatic',
    nodePaths: [path.join(root, 'node_modules')],
    alias: Object.fromEntries(
      ['components', 'api', 'utils', 'hooks', 'contexts', 'styles'].map(
        (name) => ['@' + name, path.join(source, name)]
      )
    ),
    plugins: [
      {
        name: 'demo-fixture',
        setup(plugin) {
          plugin.onLoad({ filter: /AuthContext\.tsx$/ }, () => ({
            loader: 'tsx',
            contents:
              'export const useAuth=()=>({session:null,loading:false,signOut:async()=>{}});',
          }));
          plugin.onLoad({ filter: /api\/client\.ts$/ }, () => ({
            loader: 'ts',
            contents: `export async function getSlidingBlockDemo(signal) {const r=await fetch('/sample.json',{signal});if(!r.ok)throw new Error('Unable to load sample');return r.json();}
        export async function previewSlidingBlock(inputs,revision) {const r=await fetch('/preview.json',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({inputs,revision})});if(!r.ok)throw new Error('Unable to update preview');return r.json();}`,
          }));
          plugin.onLoad({ filter: /\.module\.scss$/ }, (args) => ({
            loader: 'local-css',
            contents: sass.compile(args.path).css,
          }));
        },
      },
    ],
  });
  let fail = true;
  let previewFail = false,
    delayed = false;
  let release;
  const requests = [];
  server = http.createServer((request, response) => {
    if (request.url === '/preview.json') {
      let body = '';
      request.on('data', (chunk) => (body += chunk));
      request.on('end', () => {
        const edit = JSON.parse(body);
        requests.push(edit);
        if (previewFail) {
          response.statusCode = 503;
          response.end('{}');
          return;
        }
        const value =
          edit.inputs.block_thickness_m === 0.045
            ? cases.thicker
            : edit.inputs.block_thickness_m === 0.025
              ? cases.interference
              : sample;
        const bad = edit.inputs.block_cup_radius_m < 0.018;
        const payload = {
          revision: edit.revision,
          preview: bad ? null : value,
          findings: bad
            ? [
                {
                  code: 'unsupported_geometry',
                  field: 'block_cup_radius_m',
                  message: 'The rounded face radius is too small.',
                },
              ]
            : value.findings,
        };
        const send = () => {
          response.setHeader('Content-Type', 'application/json');
          response.end(JSON.stringify(payload));
        };
        if (delayed) release = send;
        else send();
      });
      return;
    }
    if (request.url === '/sample.json') {
      response.setHeader('Content-Type', 'application/json');
      response.statusCode = fail ? 503 : 200;
      response.end(JSON.stringify(sample));
      return;
    }
    const file =
      request.url === '/app.js'
        ? 'app.js'
        : request.url === '/app.css'
          ? 'app.css'
          : null;
    response.setHeader(
      'Content-Type',
      file?.endsWith('.js')
        ? 'text/javascript'
        : file
          ? 'text/css'
          : 'text/html'
    );
    response.end(
      file
        ? fs.readFileSync(path.join(temporary, file))
        : '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/app.css"></head><body><div id="root"></div><script type="module" src="/app.js"></script></body></html>'
    );
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  browser = await chromium.launch({
    headless: true,
    args: [
      '--no-sandbox',
      '--use-angle=swiftshader',
      '--enable-unsafe-swiftshader',
    ],
    ...(process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH }
      : {}),
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page
    .getByRole('alert')
    .filter({ hasText: 'Sample unavailable' })
    .waitFor();
  fail = false;
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await page.getByTestId('closure-value').waitFor();
  await page
    .getByRole('alert')
    .filter({ hasText: 'Face contact study' })
    .waitFor();
  await page.getByText('Pressure dependent', { exact: true }).waitFor();
  await page.getByTestId('moving-contact-span').waitFor();
  assert.equal(
    await page.getByTestId('moving-contact-span').getAttribute('stroke-width'),
    '5'
  );
  await page.locator('[data-testid="sliding-3d"] canvas').waitFor();
  const slider = page.getByRole('slider', {
    name: 'Sheave closure',
    exact: true,
  });
  await slider.press('End');
  await page
    .getByTestId('closure-value')
    .filter({ hasText: '15.00' })
    .waitFor();
  assert.equal(
    Number(await page.getByTestId('section-block').getAttribute('data-radial')),
    sample.frames.at(-1).datum_m[0]
  );
  assert.equal(
    Number(await page.getByTestId('section-block').getAttribute('data-axial')),
    sample.frames.at(-1).datum_m[1]
  );
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
  await page.waitForFunction(
    () =>
      Number(
        document
          .querySelector('[data-testid="section-block"]')
          .getAttribute('data-axial')
      ) > 0.0001
  );
  await page.getByRole('button', { name: 'Pause stroke' }).click();

  // Select real SVG features with the keyboard; fields and dimensions follow.
  await page
    .getByRole('button', { name: 'Edit reaction cup in section', exact: true })
    .press('Enter');
  await page
    .getByRole('textbox', { name: 'Cup contact radius', exact: true })
    .waitFor();
  await page.getByRole('button', { name: 'Movable ramp', exact: true }).click();
  await page
    .getByRole('textbox', { name: 'Shared ramp angle', exact: true })
    .waitFor();
  await page.getByRole('button', { name: 'Block', exact: true }).click();
  const thickness = page.getByRole('textbox', {
    name: 'Block datum thickness',
    exact: true,
  });
  const updated = () =>
    page
      .getByTestId('preview-status')
      .filter({ hasText: 'Preview updated · hardware clears' })
      .waitFor();
  await updated();
  delayed = true;
  await thickness.fill('45 mm');
  await page
    .getByTestId('preview-status')
    .filter({ hasText: 'Updating preview' })
    .waitFor();
  await page.waitForFunction(() =>
    document.body.textContent.includes('Loads unavailable')
  );
  const deadline = Date.now() + 5000;
  while (!release && Date.now() < deadline)
    await new Promise((resolve) => setTimeout(resolve, 20));
  assert.ok(release, 'The edited preview request must reach the server');
  await thickness.fill('40 mm');
  await updated();
  delayed = false;
  release();
  release = null;
  await page.waitForTimeout(100);
  assert.equal(await thickness.inputValue(), '40 mm');
  assert.equal(
    await page.getByText('Previous assembly preview', { exact: true }).count(),
    0
  );
  assert.match(
    await page.locator('footer').textContent(),
    new RegExp(((sample.total_mass_kg * 1000) / sample.block_count).toFixed(1))
  );
  await thickness.fill('45 mm');
  await thickness.press('Enter');
  await updated();
  assert.match(
    await page.locator('footer').textContent(),
    new RegExp(
      ((cases.thicker.total_mass_kg * 1000) / sample.block_count).toFixed(1)
    )
  );
  const beforeInvalid = requests.length;
  const validThicknessText = await thickness.inputValue();
  await thickness.fill('-');
  await page
    .getByTestId('preview-status')
    .filter({ hasText: 'Correct the highlighted input' })
    .waitFor();
  await page.waitForTimeout(450);
  assert.equal(requests.length, beforeInvalid);
  await thickness.fill('25 mm');
  await thickness.press('Enter');
  await page
    .getByRole('alert')
    .filter({ hasText: 'reaction cup interferes' })
    .waitFor();
  await slider.press('Home');
  assert.match(
    await page
      .getByTestId('sliding-3d')
      .getAttribute('data-hardware-interference'),
    /cup_moving/
  );
  assert.ok(
    (await page
      .getByTestId('sliding-section')
      .locator('path[stroke="#ff6269"]')
      .count()) > 0
  );
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await updated();
  assert.equal(await thickness.inputValue(), validThicknessText);
  await page.getByRole('button', { name: 'Redo', exact: true }).click();
  await page
    .getByRole('alert')
    .filter({ hasText: 'reaction cup interferes' })
    .waitFor();
  await page
    .getByRole('button', { name: 'Reset dimensions', exact: true })
    .click();
  await updated();
  const radius = page.getByRole('textbox', {
    name: 'Rounded face radius',
    exact: true,
  });
  await radius.fill('5 mm');
  await radius.press('Enter');
  await page
    .getByRole('alert')
    .filter({ hasText: 'radius is too small' })
    .waitFor();
  await page.getByText('Previous assembly preview', { exact: true }).waitFor();
  await radius.fill('20 mm');
  await radius.press('Enter');
  await updated();
  previewFail = true;
  await thickness.fill('45 mm');
  await thickness.press('Enter');
  await page
    .getByRole('alert')
    .filter({ hasText: 'Unable to update preview' })
    .waitFor();
  previewFail = false;
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await updated();
  await page
    .getByRole('button', { name: 'Reset dimensions', exact: true })
    .click();
  await updated();
  if (process.env.SLIDING_QA_DIR) {
    fs.mkdirSync(process.env.SLIDING_QA_DIR, { recursive: true });
    await page.getByTestId('sliding-3d').scrollIntoViewIfNeeded();
    await page.waitForTimeout(250); // The on-demand renderer pauses off screen.
    await page
      .getByRole('heading', { name: 'Edit the cross section', exact: true })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: path.join(process.env.SLIDING_QA_DIR, 'editable-desktop.png'),
      fullPage: true,
    });
    await page.getByTestId('sliding-section').screenshot({
      path: path.join(process.env.SLIDING_QA_DIR, 'editable-section.png'),
    });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await slider.press('End');
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth
    ),
    false
  );
  assert.equal(
    await slider.getAttribute('aria-valuetext'),
    '15.00 millimetres'
  );
  if (process.env.SLIDING_QA_DIR) {
    await page.getByTestId('sliding-3d').scrollIntoViewIfNeeded();
    await page.waitForTimeout(250);
    await page.screenshot({
      path: path.join(process.env.SLIDING_QA_DIR, 'editable-mobile.png'),
      fullPage: true,
    });
  }
  assert.deepEqual(errors, []);
  console.log(
    'PASS sliding-block WebGL, exact frames, editable SVG selection, debounced refresh, late replies, invalid text, interference, undo/redo/reset, failed contact, retry and mobile layout'
  );
} finally {
  if (browser) await browser.close();
  if (server) await new Promise((resolve) => server.close(resolve));
  fs.rmSync(temporary, { recursive: true, force: true });
}
