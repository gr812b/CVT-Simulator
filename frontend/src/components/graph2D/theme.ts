import type { EChartsOption } from 'echarts';
import type { ChartTheme, ChartConfig } from './types';
import { COLORS, LAYOUT, CHART_DEFAULTS } from './constants';

/**
 * Default dark theme for charts
 */
export const DARK_THEME: Required<ChartTheme> = {
  backgroundColor: COLORS.DARK.BACKGROUND,
  textColor: COLORS.DARK.TEXT,
  gridColor: COLORS.DARK.GRID,
  lineColor: COLORS.DARK.LINE,
  darkMode: true,
};

/**
 * Light theme for charts
 */
export const LIGHT_THEME: Required<ChartTheme> = {
  backgroundColor: COLORS.LIGHT.BACKGROUND,
  textColor: COLORS.LIGHT.TEXT,
  gridColor: COLORS.LIGHT.GRID,
  lineColor: COLORS.LIGHT.LINE,
  darkMode: false,
};

/**
 * Creates a complete theme by merging provided theme with defaults
 */
export function createTheme(userTheme: ChartTheme = {}): Required<ChartTheme> {
  const baseTheme = userTheme.darkMode === false ? LIGHT_THEME : DARK_THEME;
  return { ...baseTheme, ...userTheme };
}

/**
 * Generates ECharts styling options based on theme
 */
export function generateChartStyle(theme: Required<ChartTheme>): Partial<EChartsOption> {
  const colors = theme.darkMode ? COLORS.DARK : COLORS.LIGHT;
  
  return {
    backgroundColor: theme.backgroundColor,
    textStyle: { color: theme.textColor },
    
    title: {
      textStyle: { color: theme.textColor },
    },
    
    tooltip: {
      backgroundColor: colors.TOOLTIP_BG,
      borderColor: theme.gridColor,
      textStyle: { color: theme.textColor },
    },
    
    toolbox: {
      iconStyle: { borderColor: theme.textColor },
      emphasis: {
        iconStyle: { borderColor: theme.lineColor },
      },
    },
    
    xAxis: {
      axisLine: { lineStyle: { color: theme.gridColor } },
      axisTick: { lineStyle: { color: theme.gridColor } },
      axisLabel: { color: theme.textColor },
      nameTextStyle: { color: theme.textColor },
      splitLine: { lineStyle: { color: theme.gridColor } },
    },
    
    yAxis: {
      axisLine: { lineStyle: { color: theme.gridColor } },
      axisTick: { lineStyle: { color: theme.gridColor } },
      axisLabel: { color: theme.textColor },
      nameTextStyle: { color: theme.textColor },
      splitLine: { lineStyle: { color: theme.gridColor } },
    },
    
    dataZoom: [
      {
        textStyle: { color: theme.textColor },
        borderColor: theme.gridColor,
        fillerColor: colors.ZOOM_FILL,
        handleStyle: {
          color: theme.lineColor,
          borderColor: theme.lineColor,
        },
      },
      {
        textStyle: { color: theme.textColor },
        borderColor: theme.gridColor,
        fillerColor: colors.ZOOM_FILL,
        handleStyle: {
          color: theme.lineColor,
          borderColor: theme.lineColor,
        },
      },
    ],
  };
}

/**
 * Creates default chart configuration
 */
export function createDefaultConfig(): ChartConfig {
  return {
    height: LAYOUT.DEFAULT_HEIGHT,
    width: LAYOUT.DEFAULT_WIDTH,
    xAxis: {
      name: 'X',
      type: CHART_DEFAULTS.AXIS_TYPE,
    },
    yAxis: {
      name: 'Y',
      type: CHART_DEFAULTS.AXIS_TYPE,
    },
    smooth: CHART_DEFAULTS.SMOOTH_LINES,
    showSymbol: CHART_DEFAULTS.SHOW_SYMBOLS,
  };
}