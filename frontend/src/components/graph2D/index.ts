// Main component
export { Graph2D } from './graph2D';

// Type definitions
export type {
  DataPoint2D,
  AxisConfig,
  ChartConfig,
  ChartTheme,
  Graph2DProps,
  ValidationResult,
} from './types';

// Constants
export { COLORS, LAYOUT, VALIDATION, CHART_DEFAULTS } from './constants';

// Theme utilities
export {
  DARK_THEME,
  LIGHT_THEME,
  createTheme,
} from './theme';

// Core utilities
export {
  validateData,
  createDataFromArrays,
  inferAxisType,
} from './validation';

export {
  createChartOptions,
} from './chartOptions';

// CSV utilities (for parent components)
export {
  parseCSVSimple,
  csvToDataPoints,
  csvToVelocityData,
  getCSVColumns,
  isParsableDate,
  isNumeric,
} from './csvUtils';