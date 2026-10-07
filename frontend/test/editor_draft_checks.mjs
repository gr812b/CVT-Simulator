import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const helper = path.join(root, 'src/features/physicalLibrary/editorDraft.ts');
const compiled = ts.transpileModule(fs.readFileSync(helper, 'utf8'), {
  fileName: helper,
  reportDiagnostics: true,
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true },
});
assert.equal(compiled.diagnostics?.filter((d) => d.category === ts.DiagnosticCategory.Error).length, 0, 'editorDraft.ts syntax');
const context = { exports: {} };
vm.runInNewContext(compiled.outputText, context, { filename: helper });
const { hasUnsavedEditorDraft } = context.exports;
let count = 0;
function test(name, fn) { fn(); count++; console.log('PASS', name); }

test('untouched new forms are clean', () => {
  assert.equal(hasUnsavedEditorDraft('{"name":""}', '{"name":""}', 0), false);
});
test('document edits are dirty', () => {
  assert.equal(hasUnsavedEditorDraft('{"name":"CVT"}', '{"name":""}', 0), true);
});
test('unfinished or invalid quantity text remains dirty even before the document can represent it', () => {
  assert.equal(hasUnsavedEditorDraft('{"name":"CVT"}', '{"name":"CVT"}', 1), true);
});

test('PhysicalEditor protects navigation and provides explicit discard flows', () => {
  const source = fs.readFileSync(path.join(root, 'src/features/physicalLibrary/PhysicalEditor.tsx'), 'utf8');
  assert.match(source, /useBlocker/);
  assert.match(source, /useBeforeUnload/);
  assert.match(source, /Discard draft/);
  assert.match(source, /Discard unsaved changes\?/);
  assert.match(source, /setInvalid\(new Set\(\)\)/);
  assert.match(source, /permitNavigation\.current = true/);
  assert.match(source, /blocker\.proceed\(\)/);
});

console.log(JSON.stringify({ editorDraftChecks: count }));
