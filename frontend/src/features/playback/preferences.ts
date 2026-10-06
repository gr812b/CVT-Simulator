import { useLocalStorage } from '@mantine/hooks';
import type { ForceOptions } from '@components/scene3DViewer/forceRenderer';

/** UI preferences only. Playback data and camera/axis ranges stay with each run. */
export type ForcePreferences = Omit<ForceOptions, 'tracks'> & {
  enabled: boolean;
  selected: string[] | null;
};
export const DEFAULT_FORCES: ForcePreferences = {
  enabled: false,
  body: 'both',
  selected: null,
  components: ['axial'],
  scale: 1,
  labels: false,
};
export const DEFAULT_SCENE = {
  beltVisible: true,
  showTension: false,
  showAngularRotation: true,
  showMotionBlur: false,
  gridsVisible: false,
  orthographicView: false,
  crossSectionEnabled: false,
  modelsTransparent: false,
  forces: DEFAULT_FORCES,
};
export type ScenePreferences = typeof DEFAULT_SCENE;
export type PlotPreferences = {
  signal: string;
  tab: string;
  choices: Record<string, string[]>;
  series: Record<string, Record<string, boolean>>;
};
export const DEFAULT_PLOTS: PlotPreferences = {
  signal: 'vehicle.speed',
  tab: 'overview',
  choices: {},
  series: {},
};

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
function read(value: string | undefined): Record<string, unknown> {
  try {
    return record(JSON.parse(value ?? '{}'));
  } catch {
    return {};
  }
}
function strings(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((item) => typeof item === 'string')
  );
}
export function decodeScenePreferences(
  value: string | undefined,
): ScenePreferences {
  const saved = read(value);
  const forces = record(saved.forces);
  const scene = { ...DEFAULT_SCENE };
  for (const key of Object.keys(DEFAULT_SCENE) as (keyof ScenePreferences)[]) {
    if (key !== 'forces' && typeof saved[key] === 'boolean')
      scene[key] = saved[key];
  }
  scene.forces = {
    enabled:
      typeof forces.enabled === 'boolean'
        ? forces.enabled
        : DEFAULT_FORCES.enabled,
    body:
      forces.body === 'primary' || forces.body === 'secondary'
        ? forces.body
        : 'both',
    selected: strings(forces.selected) ? forces.selected : null,
    components: strings(forces.components)
      ? forces.components.filter((key) =>
          ['axial', 'radial', 'tangential'].includes(key),
        )
      : DEFAULT_FORCES.components,
    scale:
      typeof forces.scale === 'number' && Number.isFinite(forces.scale)
        ? Math.min(3, Math.max(0.25, forces.scale))
        : DEFAULT_FORCES.scale,
    labels:
      typeof forces.labels === 'boolean'
        ? forces.labels
        : DEFAULT_FORCES.labels,
  };
  return scene;
}
export function decodePlotPreferences(
  value: string | undefined,
): PlotPreferences {
  const saved = read(value);
  return {
    signal:
      typeof saved.signal === 'string' ? saved.signal : DEFAULT_PLOTS.signal,
    tab: typeof saved.tab === 'string' ? saved.tab : DEFAULT_PLOTS.tab,
    choices: Object.fromEntries(
      Object.entries(record(saved.choices))
        .filter((entry): entry is [string, string[]] => strings(entry[1]))
        .map(([key, value]) => [key, value.slice(0, 4)]),
    ),
    series: Object.fromEntries(
      Object.entries(record(saved.series)).map(([key, value]) => [
        key,
        Object.fromEntries(
          Object.entries(record(value)).filter(
            (entry) => typeof entry[1] === 'boolean',
          ),
        ),
      ]),
    ) as PlotPreferences['series'],
  };
}
export function useScenePreferences() {
  return useLocalStorage<ScenePreferences>({
    key: 'cinder-scene-preferences-v1',
    defaultValue: DEFAULT_SCENE,
    deserialize: decodeScenePreferences,
    getInitialValueInEffect: false,
  });
}
export function usePlotPreferences() {
  return useLocalStorage<PlotPreferences>({
    key: 'cinder-plot-preferences-v1',
    defaultValue: DEFAULT_PLOTS,
    deserialize: decodePlotPreferences,
    getInitialValueInEffect: false,
  });
}
