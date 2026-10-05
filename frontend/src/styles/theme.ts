import { Button, createTheme, type CSSVariablesResolver } from '@mantine/core';

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
  components: { Button: Button.extend({ defaultProps: { fw: 600 } }) },
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
  primary: '#e85959',
  secondary: '#4db6ac',
  aluminium: '#cbd4df',
  fixedSheave: '#aab8cc',
  movingSheave: '#eabf75',
  flyweight: '#dd795a',
  roller: '#dee4ed',
  ramp: '#77b3d5',
  helix: '#72c1a5',
  shaft: '#8795a8',
  spring: '#657389',
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
