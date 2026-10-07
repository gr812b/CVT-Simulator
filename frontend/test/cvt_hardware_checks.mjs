import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import ts from 'typescript';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const source = path.join(root, 'src/features/physicalLibrary/cvtHardware.ts');
const compiled = ts.transpileModule(fs.readFileSync(source, 'utf8'), {
  fileName: source,
  reportDiagnostics: true,
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.CommonJS,
    strict: true,
  },
});
assert.equal(
  compiled.diagnostics?.filter((item) => item.category === ts.DiagnosticCategory.Error).length,
  0,
  'cvtHardware.ts syntax',
);
const context = { exports: {}, console };
context.require = (name) => {
  throw new Error(`Unexpected runtime dependency: ${name}`);
};
vm.runInNewContext(compiled.outputText, context, { filename: source });
const h = context.exports;

const belt = (height_m, half_angle_rad = 0.2) => ({
  revision_id: 'belt-r1', name: 'Belt', description: '', source_label: '', source_url: '', source_notes: '',
  data: {
    height_m, half_angle_rad, outer_width_m: 0.02, inner_width_m: 0.016,
    outer_length_m: 0.95, cord_depth_from_outer_m: 0.0025, density_kg_per_m3: 1100,
    length_reference: 'outer',
  },
});
const make = () => ({
  belt: belt(0.0155702, 0.2007),
  assembly: {
    geometry: {
      primary_outer_radius_at_zero_shift_m: 0.0362077,
      secondary_outer_radius_at_zero_shift_m: 0.1016,
      max_shift_m: 0.01905,
      deadzone_shift_m: 0.0025,
      sheave_half_angle_rad: 0.2007,
      belt: { height_m: 0.0155702 },
    },
    inertias: {
      primary: {
        fixed_rotating_hardware_inertia_kg_m2: 0.003,
        movable_sheave_rotational_inertia_kg_m2: 0.002,
        moving_sheave_mass_kg: 1.0,
      },
      secondary: {
        fixed_rotating_hardware_inertia_kg_m2: 0.004,
        movable_sheave_rotational_inertia_kg_m2: 0.005,
        moving_sheave_mass_kg: 0.7,
      },
      belt_density_kg_per_m3: 1100,
    },
    contact: { static_friction_coefficient: 0.65, kinetic_friction_coefficient: 0.55 },
    pulleys: {
      primary: {
        components: [
          {
            kind: 'fixed_pivot_roller_flyweight',
            geometry: {
              pivot_axial_position_m: 0,
              pivot_radius_m: 0.042,
              arm_length_m: 0.031,
              roller_radius_m: 0.0065,
              ramp_reference_axial_position_m: 0.038,
              ramp_reference_radius_m: 0.049,
              ramp_profile: { kind: 'piecewise_ramp', segments: [] },
              ramp_axial_direction: -1,
              axial_position_min_m: 0,
              axial_position_max_m: 0.01905,
              roller_side_sign: 1,
              root_scan_points: 513,
              validation_positions: 129,
              root_residual_tolerance_m2: 1e-14,
              coordinate_tolerance_m: 1e-10,
              compilation_points: 257,
            },
            mass_geometry: {},
          },
          { kind: 'axial_spring', stiffness_N_per_m: 12000, initial_compression_m: 0.09, compression_per_axial_position: 1 },
        ],
        helical_coupling: null,
      },
      secondary: {
        components: [],
        helical_coupling: {
          profile: { radius_m: 0.044, circumferential_profile: { kind: 'piecewise_ramp', segments: [] } },
          opening_per_axial_position: -1,
          opening_offset_m: 0,
        },
      },
    },
  },
});

let count = 0;
function test(name, fn) { fn(); count++; console.log('PASS', name); }
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-12, `${a} != ${b}`);

test('primary shaft radius is derived from the stored outer-belt radius and selected belt height', () => {
  near(h.primaryShaftRadius(make()), 0.0206375);
});

test('changing belts preserves shaft radius while recomputing CINDER outer-belt radius', () => {
  const value = make();
  const before = h.primaryShaftRadius(value);
  const next = h.withBeltPreservingPrimaryShaft(value, belt(0.012, 0.24));
  near(h.primaryShaftRadius(next), before);
  near(next.assembly.geometry.primary_outer_radius_at_zero_shift_m, before + 0.012);
  near(next.assembly.geometry.sheave_half_angle_rad, 0.24);
  near(value.assembly.geometry.primary_outer_radius_at_zero_shift_m, 0.0362077);
});

test('editing shaft radius maps back to the existing CINDER outer-belt radius without changing belt data', () => {
  const value = make();
  const next = h.withPrimaryShaftRadius(value, 0.025);
  near(next.assembly.geometry.primary_outer_radius_at_zero_shift_m, 0.025 + value.belt.data.height_m);
  assert.equal(next.belt, value.belt);
});

test('uncoupled primary exposes the fixed plus movable rotating hardware inertia as one total', () => {
  const value = make();
  assert.equal(h.primaryHasRelativeRotationCoupling(value), false);
  near(h.primaryRotatingHardwareInertia(value), 0.005);
  const next = h.withPrimaryRotatingHardwareInertia(value, 0.01);
  near(next.assembly.inertias.primary.fixed_rotating_hardware_inertia_kg_m2, 0.006);
  near(next.assembly.inertias.primary.movable_sheave_rotational_inertia_kg_m2, 0.004);
  near(h.primaryRotatingHardwareInertia(next), 0.01);
});

test('a primary relative-rotation coupling keeps the separate-inertia path available', () => {
  const value = make();
  value.assembly.pulleys.primary.helical_coupling = { profile: {}, opening_per_axial_position: 1, opening_offset_m: 0 };
  assert.equal(h.primaryHasRelativeRotationCoupling(value), true);
});

test('ordinary primary contact checking is zero-based and follows available travel', () => {
  const value = make();
  assert.equal(h.usesOrdinaryPrimaryTravel(value), true);
  const next = h.withAvailablePrimaryTravel(value, 0.022);
  assert.equal(next.assembly.geometry.max_shift_m, 0.022);
  const geometry = next.assembly.pulleys.primary.components[0].geometry;
  assert.equal(geometry.axial_position_min_m, 0);
  assert.equal(geometry.axial_position_max_m, 0.022);
});

test('custom legacy contact bounds are preserved when ordinary travel changes', () => {
  const value = make();
  value.assembly.pulleys.primary.components[0].geometry.axial_position_min_m = -0.001;
  value.assembly.pulleys.primary.components[0].geometry.axial_position_max_m = 0.025;
  assert.equal(h.usesOrdinaryPrimaryTravel(value), false);
  const next = h.withAvailablePrimaryTravel(value, 0.021);
  const geometry = next.assembly.pulleys.primary.components[0].geometry;
  assert.equal(next.assembly.geometry.max_shift_m, 0.021);
  assert.equal(geometry.axial_position_min_m, -0.001);
  assert.equal(geometry.axial_position_max_m, 0.025);
});

test('absolute ramp reference coordinates are tune-only, not CVT hardware fields', () => {
  assert.equal(h.isCvtHardwareField('/pulleys/primary/components/*/geometry/ramp_reference_axial_position_m'), false);
  assert.equal(h.isCvtHardwareField('/pulleys/primary/components/*/geometry/ramp_reference_radius_m'), false);
  assert.equal(h.isCvtHardwareField('/pulleys/primary/components/*/geometry/pivot_radius_m'), true);
});

test('mechanical mappings and compilation controls are advanced with physical labels', () => {
  const field = { label: 'Compression per axial position', description: '', advanced: false };
  const spring = h.cvtFieldPresentation(field, '/pulleys/primary/components/1/compression_per_axial_position');
  assert.equal(spring.advanced, true);
  assert.match(spring.label, /Spring compression/);
  const travel = h.cvtFieldPresentation({ ...field, label: 'Max shift' }, '/geometry/max_shift_m');
  assert.equal(travel.advanced, false);
  assert.equal(travel.label, 'Available primary travel');
});

for (const relative of [
  'src/features/physicalLibrary/CvtEditor.tsx',
  'src/features/publicLibrary/ConfigurationView.tsx',
]) {
  const filename = path.join(root, relative);
  const parsed = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename,
    reportDiagnostics: true,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX, strict: true },
  });
  assert.equal(parsed.diagnostics?.filter((item) => item.category === ts.DiagnosticCategory.Error).length, 0, relative);
}

test('editor source uses the physical shaft, combined inertia and component-level advanced flow', () => {
  const text = fs.readFileSync(path.join(root, 'src/features/physicalLibrary/CvtEditor.tsx'), 'utf8');
  assert.match(text, /Primary shaft radius/);
  assert.match(text, /Primary rotating hardware inertia/);
  assert.match(text, /Advanced mechanical settings/);
  assert.match(text, /withBeltPreservingPrimaryShaft/);
  assert.doesNotMatch(text, /Show advanced geometry compilation settings/);
});

console.log(JSON.stringify({ cvtHardwareChecks: count, syntaxFiles: 2 }));
