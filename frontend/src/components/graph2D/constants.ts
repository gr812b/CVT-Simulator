/**
 * Chart Constants
 */

export const COLORS = {
  DARK: {
    BACKGROUND: '#1e1e1e',
    TEXT: '#ffffff',
    GRID: '#404040',
    LINE: '#4dabf7',
    TOOLTIP_BG: '#2a2a2a',
    ZOOM_FILL: 'rgba(77, 171, 247, 0.2)',
  },
  
  LIGHT: {
    BACKGROUND: '#ffffff',
    TEXT: '#333333',
    GRID: '#e0e0e0',
    LINE: '#1976d2',
    TOOLTIP_BG: '#ffffff',
    ZOOM_FILL: 'rgba(25, 118, 210, 0.2)',
  },
  
  ERROR: '#ff4444',
} as const;

export const LAYOUT = {
  DEFAULT_HEIGHT: 400,
  DEFAULT_WIDTH: '100%',
  
  GRID: {
    LEFT: 60,
    RIGHT: 20,
    TOP_WITH_TITLE: 60,
    TOP_WITHOUT_TITLE: 40,
    BOTTOM: 60,
  },
  
  TITLE: {
    TOP: 16,
  },
  
  TOOLBOX: {
    RIGHT: 12,
    TOP: 12,
  },
  
  X_AXIS_NAME_GAP: 30,
  Y_AXIS_NAME_GAP: 40,
  SLIDER_BOTTOM: 10,
} as const;

export const VALIDATION = {
  MIN_DATA_POINTS_WARNING: 5,
  SINGLE_POINT_WARNING: 1,
  DATE_DETECTION_THRESHOLD: 0.8,
  HEADER_ROW_INDEX: 0,
  FIRST_DATA_ROW_INDEX: 1,
  NOT_FOUND_INDEX: -1,
} as const;

export const CHART_DEFAULTS = {
  SMOOTH_LINES: true,
  SHOW_SYMBOLS: false,
  AXIS_TYPE: 'value' as const,
  BOUNDARY_GAP: false,
  HIDE_OVERLAP: true,
  SHOW_SPLIT_LINES: true,
} as const;