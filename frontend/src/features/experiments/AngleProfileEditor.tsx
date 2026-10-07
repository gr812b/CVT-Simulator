import { useState } from 'react';
import { Alert, Group, Paper, SimpleGrid, Stack, Text } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import { useAuth } from '@contexts/AuthContext';
import { formatPreferredQuantity, normalizeUnitPreferences } from '@utils/units';
import type { TuneProfileTrace } from './api';
import { ProfileSketch } from './ProfileSketch';
import {
  constantProfile, convertToAngleStages, displayAngle, endpointAngles, MAX_PROFILE_ANGLE,
  MIN_HELIX_ANGLE, primaryAngleStages, readAngleStages, readTravelStages, splitStage, storedAngle, writeAngleStages, writeTravelStages,
  type AngleStages, type Ramp, type RampField,
} from './profileStages';

export function AngleProfileEditor({ field, value, onChange, readOnly, trace, contact }: {
  field: RampField; value: Ramp; onChange: (next: Ramp) => void; readOnly: boolean;
  trace?: TuneProfileTrace | null; contact?: number | null;
}) {
  const { unitPreferences } = useAuth();
  const preferences = normalizeUnitPreferences(unitPreferences);
  const helix = field.angle_convention === 'helix';
  const [selected, setSelected] = useState(0);
  const [showStages, setShowStages] = useState(() => !(value.segments.length === 1 && value.segments[0].kind === 'linear_segment'));
  const [replace, setReplace] = useState<'stages' | 'constant' | null>(null);
  const total = value.segments.reduce((sum, segment) => sum + segment.length_m, 0);
  const used: [number, number] | undefined = helix && trace?.used_start_m != null && trace.used_end_m != null && trace.used_end_m > trace.used_start_m
    ? [trace.used_start_m, trace.used_end_m] : undefined;
  const savedStages = used ? readTravelStages(value, used) : readAngleStages(value);
  const guided = helix ? savedStages : primaryAngleStages(value);
  const index = Math.min(selected, (guided?.stages.length ?? value.segments.length) - 1);
  const angleMin = helix ? MIN_HELIX_ANGLE : -MAX_PROFILE_ANGLE;
  const angleMax = MAX_PROFILE_ANGLE;
  const change = (next: AngleStages) => onChange(used ? writeTravelStages(next, used, total) : writeAngleStages(next));
  const position = (m: number) => used ? (m - used[0]) / (used[1] - used[0]) * 100 : m;
  const coordinate = (display: number) => used ? used[0] + display / 100 * (used[1] - used[0]) : display;
  const formatPosition = (m: number) => used
    ? `${Math.min(100, Math.max(0, position(m))).toFixed(1)}%`
    : formatPreferredQuantity(m, 'length', 'hardware', preferences, 'mm', 2);
  const previewReady = !helix || !!used;
  const validAngle = (a: number) => a >= angleMin - 1e-12 && a <= angleMax + 1e-12;
  const constant = !showStages && guided?.stages.length === 1 && Math.abs(guided.start_angle_rad - guided.stages[0].angle_rad) < 1e-10;
  const ranges: [number, number][] | undefined = guided?.stages.map((stage, i) => [guided.stages[i - 1]?.end_m ?? used?.[0] ?? 0, stage.end_m]);
  return <Stack gap="sm">
    <Text size="sm" c="dimmed">{helix
      ? 'Helix angle is measured from the circumferential direction. Positions use the usable secondary opening, not the total machined profile length.'
      : 'Ramp angle describes the surface slope, not the flyweight arm angle. Positions are measured along the ramp’s axial coordinate; use the travel slider to see where the roller actually touches.'}</Text>
    <ProfileSketch trace={trace} profile={value} selected={index} onSelect={setSelected} contact={contact} helix={helix} ranges={ranges}/>
    {!helix && !savedStages && <Text size="xs" c="dimmed">
      The saved custom curvature is retained until you make a profile edit. Angle edits use shared endpoint angles and automatic smooth joins; the plot shows the actual current shape.
    </Text>}
    {!guided && <Alert color="blue" title="Saved profile retained">
      This profile uses {used ? 'custom joins or a curve that crosses the usable opening boundaries' : 'a custom arc or custom smooth joins'}. Opening it does not change its shape. Angle-stage editing is an explicit conversion.
    </Alert>}
    {helix && !used && <Text size="sm" c="dimmed">A valid preview is needed to express stage positions as opening percentages. Existing profile values are retained.</Text>}
    {guided && (readOnly ? <Stack gap={4}>
      <Text size="sm">Starting {helix ? 'helix' : 'ramp'} angle: {(displayAngle(guided.start_angle_rad, helix) * 180 / Math.PI).toFixed(2)}°</Text>
      {guided.stages.map((stage, i) => <Text key={i} size="sm">Stage {i + 1}: {formatPosition(guided.stages[i - 1]?.end_m ?? used?.[0] ?? 0)} → {formatPosition(stage.end_m)} · end angle {(displayAngle(stage.angle_rad, helix) * 180 / Math.PI).toFixed(2)}°</Text>)}
    </Stack> : constant ? <Stack gap="xs">
      <QuantityInput scope="hardware" label={helix ? 'Helix angle' : 'Ramp angle'} unit="°" scale={180 / Math.PI}
        value={displayAngle(guided.start_angle_rad, helix)} min={angleMin} max={angleMax}
        onChange={a => { if (validAngle(a)) onChange(constantProfile(total, storedAngle(a, helix))); }}/>
      {!helix && <QuantityInput scope="hardware" label="Ramp axial extent" unit="mm" scale={1000} min={1e-6} value={total}
        onChange={length => { if (length >= 1e-6) onChange(constantProfile(length, guided.start_angle_rad)); }}/>}
      <Button variant="light" size="xs" disabled={!previewReady} onClick={() => { setShowStages(true); change(splitStage(guided, 0, used)); }}>Add angle stages</Button>
    </Stack> : <>
      <QuantityInput scope="hardware" label={`Starting ${helix ? 'helix' : 'ramp'} angle`} unit="°" scale={180 / Math.PI}
        value={displayAngle(guided.start_angle_rad, helix)} min={angleMin} max={angleMax}
        onChange={a => { if (validAngle(a)) change({ ...guided, start_angle_rad: storedAngle(a, helix) }); }}/>
      {guided.stages.map((stage, i) => {
        const last = i === guided.stages.length - 1;
        const previous = guided.stages[i - 1];
        return <Paper key={i} withBorder p="sm" style={i === index ? { borderColor: 'var(--mantine-primary-color-filled)' } : undefined}>
          <Stack gap="xs">
            <Button variant="subtle" size="compact-sm" onClick={() => setSelected(i)}>
              Stage {i + 1} · {formatPosition(previous?.end_m ?? used?.[0] ?? 0)} → {formatPosition(stage.end_m)}
            </Button>
            <Text size="xs" c="dimmed">Starts at {(displayAngle(previous?.angle_rad ?? guided.start_angle_rad, helix) * 180 / Math.PI).toFixed(2)}°. {i ? 'The starting angle is shared with the previous stage.' : 'The first stage uses the starting angle above.'}</Text>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              {helix && last ? <Text size="sm">Continues through 100% opening.</Text> : <QuantityInput
                scope="hardware"
                label={`Stage ${i + 1} ends at`} value={position(stage.end_m)}
                unit={used ? '%' : 'mm'} scale={used ? 1 : 1000} disabled={!previewReady}
                min={used ? position(Math.max(previous?.end_m ?? 0, used[0])) + 0.01 : (previous?.end_m ?? 0) + 1e-6}
                max={last ? undefined : used ? Math.min(100, position(guided.stages[i + 1].end_m)) - 0.01 : guided.stages[i + 1].end_m - 1e-6}
                onChange={n => {
                  const end = coordinate(n);
                  const lower = Math.max(previous?.end_m ?? 0, used?.[0] ?? 0);
                  const upper = last ? Infinity : Math.min(guided.stages[i + 1].end_m, used?.[1] ?? Infinity);
                  if (end <= lower + 1e-8 || end >= upper - 1e-8) return;
                  change({ ...guided, stages: guided.stages.map((s, k) => k === i ? { ...s, end_m: end } : s) });
                }}/>}
              <QuantityInput scope="hardware" label={`Stage ${i + 1} end angle`} unit="°" scale={180 / Math.PI}
                value={displayAngle(stage.angle_rad, helix)} min={angleMin} max={angleMax}
                onChange={a => { if (validAngle(a)) change({ ...guided, stages: guided.stages.map((s, k) => k === i ? { ...s, angle_rad: storedAngle(a, helix) } : s) }); }}/>
            </SimpleGrid>
          </Stack>
        </Paper>;
      })}
      <Text size="xs" c="dimmed">Equal start and end angles give a constant-angle stage. Different angles create a smooth transition; adjacent stages join automatically. Adding or removing a stage is a shape edit.</Text>
      <Group>
        <Button variant="light" size="xs" disabled={!previewReady || guided.stages.length >= 24}
          onClick={() => change(splitStage(guided, index, used))}>Split selected stage</Button>
        <Button variant="subtle" size="xs" disabled={guided.stages.length <= 1}
          onClick={() => {
            const stages = structuredClone(guided.stages);
            if (index === 0) stages.splice(0, 1);
            else { stages[index - 1] = { ...stages[index] }; stages.splice(index, 1); }
            setSelected(Math.max(0, index - 1)); change({ ...guided, stages });
          }}>Remove selected stage</Button>
      </Group>
    </>)}
    {helix && used && total > used[1] + 1e-8 && <Text size="xs" c="dimmed">The saved profile extends beyond the usable travel. Angle edits retain that extra length at the endpoint angle. The final stage angle is reached at 100% opening, not at the end of the extra material.</Text>}
    {!readOnly && <Group>
      {!guided && <Button variant="light" size="xs" disabled={!previewReady} onClick={() => setReplace('stages')}>Edit with angle stages</Button>}
      <Button variant="subtle" size="xs" onClick={() => {
        if (helix) { setReplace('constant'); return; }
        const angle = displayAngle(endpointAngles(value.segments[0])[0], false);
        onChange(constantProfile(total, Math.max(angleMin, Math.min(angleMax, angle))));
        setShowStages(false); setSelected(0);
      }}>Use constant angle</Button>
    </Group>}
    {helix && replace && <Paper withBorder p="md">
      <Stack>
        <Text fw={600}>Replace the profile shape?</Text>
        <Text>{replace === 'constant'
          ? 'This replaces the whole profile with one constant angle while keeping its length. The starting angle will be brought into the displayed input range if necessary.'
          : 'This retains the endpoint angles but replaces custom curvature with automatic smooth joins. For the helix, the saved endpoint angles are applied at 0% and 100% opening; extra profile length uses the endpoint angle. The shape will change.'} Nothing is saved until you save the tune.</Text>
        <Group justify="flex-end">
          <Button data-autofocus variant="default" onClick={() => setReplace(null)}>Keep current profile</Button>
          <Button onClick={() => {
            if (replace === 'constant') {
              const current = displayAngle(endpointAngles(value.segments[0])[0], helix);
              onChange(constantProfile(total, storedAngle(Math.max(angleMin, Math.min(angleMax, current)), helix)));
            } else if (used) {
              const full = readAngleStages(convertToAngleStages(value))!;
              const next = { ...full, stages: full.stages.map((stage, i) => ({ ...stage, end_m: used[0] + (used[1] - used[0]) * (i + 1) / full.stages.length })) };
              onChange(writeTravelStages(next, used, total));
            } else onChange(convertToAngleStages(value));
            setShowStages(replace !== 'constant'); setSelected(0); setReplace(null);
          }}>Replace shape</Button>
        </Group>
      </Stack>
    </Paper>}
  </Stack>;
}
