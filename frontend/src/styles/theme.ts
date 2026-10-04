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
