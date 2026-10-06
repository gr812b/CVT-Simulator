import type { components } from '@api/generated/backend';
import {
  Button,
  Popover,
  Menu,
  Tooltip,
  createTheme,
  type CSSVariablesResolver,
} from '@mantine/core';

export const overlayLayers = {
  dropdown: 80,
  modal: 200,
  modalDropdown: 300,
} as const;

/** Product palette and component defaults: keep new styling here. */
export const theme = createTheme({
  primaryColor: 'red',
  primaryShade: 7,
  defaultRadius: 'md',
  fontFamily: 'Inter, system-ui, sans-serif',
  headings: { fontFamily: 'Inter, system-ui, sans-serif' },
  colors: {
    dark: [
      '#d9dce3',
      '#b5b9c5',
      '#9399aa',
      '#626b7d',
      '#424b5c',
      '#303949',
      '#252d3a',
      '#1b2330',
      '#141b25',
      '#0f151e',
    ],
  },
  components: {
    Popover: Popover.extend({
      defaultProps: { zIndex: overlayLayers.dropdown, hideDetached: true },
    }),
    Menu: Menu.extend({ defaultProps: { zIndex: overlayLayers.dropdown } }),
    Button: Button.extend({ defaultProps: { fw: 600 } }),
    Tooltip: Tooltip.extend({
      styles: { tooltip: { backgroundColor: '#0f151e', color: '#ffffff' } },
    }),
  },
});

// Existing engineering views consume these aliases during their gradual migration.
export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {
    '--primary': 'var(--mantine-primary-color-filled)',
    '--text-color': 'var(--mantine-color-text)',
    '--background': 'var(--mantine-color-body)',
    '--secondary': 'var(--mantine-color-dark-6)',
    '--accent': 'var(--mantine-color-dark-5)',
    '--border-color': 'var(--mantine-color-dark-2)',
    '--code-background': 'var(--mantine-color-dark-8)',
    '--grid-color': 'var(--mantine-color-dark-4)',
    '--tooltip-bg': 'var(--mantine-color-dark-6)',
    '--confirm': 'var(--mantine-color-teal-6)',
    '--error': 'var(--mantine-color-red-5)',
    '--reject': 'var(--mantine-color-red-7)',
    '--warning': 'var(--mantine-color-yellow-5)',
    '--line1': 'var(--mantine-color-red-5)',
    '--line2': 'var(--mantine-color-teal-5)',
    '--line3': 'var(--mantine-color-blue-5)',
    '--line4': 'var(--mantine-color-orange-5)',
    '--line5': 'var(--mantine-color-violet-5)',
    '--line6': 'var(--mantine-color-yellow-5)',
    '--line7': 'var(--mantine-color-cyan-5)',
    '--line8': 'var(--mantine-color-pink-5)',
    '--line9': 'var(--mantine-color-grape-5)',
  },
  light: {},
  dark: {},
});

/** Shared 3D art direction. These are visual materials, not hardware properties. */
export const sceneAppearance = {
  forces: {
    resultant: '#ffd166',
    axial: '#50d8ed',
    radial: '#ef83bb',
    tangential: '#91d779',
    torque: '#b8a1ff',
  },
  primary: '#e85959',
  secondary: '#4db6ac',
  aluminium: '#cbd4df',
  fixedSheave: '#aab8cc',
  movingSheave: '#eabf75',
  shaft: '#8795a8',
  spring: '#b6a5c9',
  shaftExtension: 0.8,
  belt: '#333e50',
  unavailable: '#818b9a',
  grid: '#424b5c',
  ghostOpacity: 0.22,
  metalness: 0.5,
  roughness: 0.36,
  radialSegments: 72,
  maxPixelRatio: 2,
  mechanism: {
    trackCount: 3,
    springTurns: 6,
    maxPanelAngle: 0.14,
    // Schematic hardware dimensions, expressed relative to belt height.
    clearance: 0.12,
    slotClearance: 0.002,
    wall: 0.18,
    secondaryRoller: 0.25,
    guideRoller: 0.18,
    springWire: 0.055,
  },
  light: { sky: '#f1f5ff', ground: '#69778c', intensity: 2.1 },
} as const;

/** One status palette across run lists, detail pages and Activity. */
export const runStatusColors: Record<
  components['schemas']['RunStatusResponse']['status'],
  string
> = {
  queued: 'violet',
  validating: 'cyan',
  running: 'blue',
  completed: 'teal',
  failed: 'red',
  timed_out: 'orange',
  cancelled: 'gray',
};

/** A processed job can still end at a vehicle, model, or solver limit. */
export const runOutcomeColors: Record<
  NonNullable<components['schemas']['RunStatusResponse']['outcome']>['category'],
  string
> = {
  pending: 'blue',
  success: 'teal',
  vehicle_stopped: 'yellow',
  model_limit: 'yellow',
  numerical_error: 'red',
  configuration_error: 'orange',
  internal_error: 'red',
  service_error: 'orange',
  resource_limit: 'orange',
  cancelled: 'gray',
};
