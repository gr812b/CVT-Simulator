import type { EChartsOption, MarkLineComponentOption } from 'echarts';
import type { ChartConfig } from './types';
import { inferAxisType } from './validation';

/**
 * Gets color values from CSS custom properties defined in _colors.scss
 */
function getCSSColor(property: string, fallback: string): string {
  if (typeof window !== 'undefined') {
    const value = getComputedStyle(document.documentElement).getPropertyValue(property).trim();
    return value || fallback;
  }
  return fallback;
}

// Chart colors linked to _colors.scss
const COLORS = {
  get BACKGROUND() { return getCSSColor('--secondary', '#222222'); },
  get TEXT() { return getCSSColor('--text-color', '#ffffff'); },
  get GRID() { return getCSSColor('--grid-color', '#404040'); },
  get LINE() { return getCSSColor('--accent', '#bb0808'); },
  get TOOLTIP_BG() { return getCSSColor('--tooltip-bg', '#2a2a2a'); },
  get ZOOM_FILL() { 
    const accent = getCSSColor('--accent', '#bb0808');
    const hex = accent.replace('#', '');
    const r = parseInt(hex.substr(0, 2), 16);
    const g = parseInt(hex.substr(2, 2), 16);
    const b = parseInt(hex.substr(4, 2), 16);
    return `rgba(${r}, ${g}, ${b}, 0.2)`;
  },
  get ERROR() { return getCSSColor('--error', '#c00f0c'); },
} as const;

const LAYOUT = {
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

const CHART_DEFAULTS = {
  SMOOTH_LINES: true,
  SHOW_SYMBOLS: false,
  AXIS_TYPE: 'value' as const,
  BOUNDARY_GAP: false,
  HIDE_OVERLAP: true,
  SHOW_SPLIT_LINES: true,
} as const;

/**
 * Deep merge function for objects
 */
function deepMerge<T extends Record<string, unknown>>(target: T, source: Partial<T>): T {
  const result = { ...target };
  
  for (const key in source) {
    if (source[key] !== undefined) {
      if (typeof source[key] === 'object' && source[key] !== null && !Array.isArray(source[key])) {
        result[key] = deepMerge(
          (result[key] as Record<string, unknown>) || {},
          source[key] as Record<string, unknown>
        ) as T[Extract<keyof T, string>];
      } else {
        result[key] = source[key] as T[Extract<keyof T, string>];
      }
    }
  }
  
  return result;
}

/**
 * Creates default chart configuration
 */
function createDefaultConfig(): ChartConfig {
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

/**
 * Creates a complete chart configuration by merging user config with defaults
 */
export function createChartConfig(userConfig: Partial<ChartConfig>, xData: number[], yData: number[]): ChartConfig {
  const defaultConfig = createDefaultConfig();
  const mergedConfig: ChartConfig = {
    ...defaultConfig,
    ...userConfig,
    xAxis: {
      ...defaultConfig.xAxis,
      ...userConfig.xAxis,
    },
    yAxis: {
      ...defaultConfig.yAxis,
      ...userConfig.yAxis,
    },
  };
  
  // Auto-infer axis types if not specified
  if (xData.length > 0 && !userConfig.xAxis?.type) {
    mergedConfig.xAxis.type = inferAxisType(xData);
  }
  if (yData.length > 0 && !userConfig.yAxis?.type) {
    mergedConfig.yAxis.type = inferAxisType(yData);
  }
  
  return mergedConfig;
}

/**
 * Converts data points to ECharts dataset format
 */
export function createDataset(xData: number[], yData: number[], config: ChartConfig): EChartsOption['dataset'] {
  const source: (string | number | Date)[][] = [[config.xAxis.name, config.yAxis.name]];
  xData.forEach((x, index) => {
    const y = yData[index];
    source.push([x, y]);
  });
  return { source };
}

/**
 * Generates complete ECharts options with dark theme defaults
 */
export function generateEChartsOptions(
  xData: number[],
  yData: number[],
  config: ChartConfig,
  userOptions: Partial<EChartsOption> = {}
): EChartsOption {
  const dataset = createDataset(xData, yData, config);

  // Create axis options separately to avoid type inference issues
  const xAxisOption = {
    type: config.xAxis.type,
    name: config.xAxis.name,
    nameLocation: 'middle' as const,
    nameGap: LAYOUT.X_AXIS_NAME_GAP,
    nameTextStyle: { color: COLORS.TEXT },
    boundaryGap: config.xAxis.type === 'category',
    axisLabel: { 
      hideOverlap: CHART_DEFAULTS.HIDE_OVERLAP,
      color: COLORS.TEXT 
    },
    axisLine: { lineStyle: { color: COLORS.GRID } },
    axisTick: { lineStyle: { color: COLORS.GRID } },
    splitLine: { lineStyle: { color: COLORS.GRID } },
  };
  
  const yAxisOption = {
    type: config.yAxis.type,
    name: config.yAxis.name,
    nameLocation: 'middle' as const,
    nameGap: LAYOUT.Y_AXIS_NAME_GAP,
    nameTextStyle: { color: COLORS.TEXT },
    axisLabel: { 
      hideOverlap: CHART_DEFAULTS.HIDE_OVERLAP,
      color: COLORS.TEXT 
    },
    splitLine: { 
      show: CHART_DEFAULTS.SHOW_SPLIT_LINES,
      lineStyle: { color: COLORS.GRID }
    },
    axisLine: { lineStyle: { color: COLORS.GRID } },
    axisTick: { lineStyle: { color: COLORS.GRID } },
  };
  
  // Base options with dark theme styling built-in
  const baseOptions: EChartsOption = {
    backgroundColor: COLORS.BACKGROUND,
    textStyle: { color: COLORS.TEXT },
    
    title: config.title ? {
      text: config.title,
      left: 'center',
      top: LAYOUT.TITLE.TOP,
      textStyle: { color: COLORS.TEXT },
    } : undefined,
    
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: COLORS.TOOLTIP_BG,
      borderColor: COLORS.GRID,
      textStyle: { color: COLORS.TEXT },
    },
    
    toolbox: {
      feature: {
        dataZoom: { yAxisIndex: 'none' },
        restore: {},
        saveAsImage: {},
      },
      right: LAYOUT.TOOLBOX.RIGHT,
      top: LAYOUT.TOOLBOX.TOP,
      iconStyle: { borderColor: COLORS.TEXT },
      emphasis: {
        iconStyle: { borderColor: COLORS.LINE },
      },
    },
    
    dataset,
    
    grid: {
      left: LAYOUT.GRID.LEFT,
      right: LAYOUT.GRID.RIGHT,
      top: config.title ? LAYOUT.GRID.TOP_WITH_TITLE : LAYOUT.GRID.TOP_WITHOUT_TITLE,
      bottom: LAYOUT.GRID.BOTTOM,
      containLabel: true,
    },
    
    xAxis: xAxisOption,
    
    yAxis: yAxisOption,
    
    dataZoom: [
      { 
        type: 'inside', 
        xAxisIndex: 0 
      },
      { 
        type: 'slider', 
        xAxisIndex: 0, 
        bottom: LAYOUT.SLIDER_BOTTOM,
        textStyle: { color: COLORS.TEXT },
        borderColor: COLORS.GRID,
        fillerColor: COLORS.ZOOM_FILL,
        handleStyle: {
          color: COLORS.LINE,
          borderColor: COLORS.LINE,
        },
      },
    ],
    
    series: [
      {
        type: 'line',
        name: config.seriesName || `${config.yAxis.name} vs ${config.xAxis.name}`,
        smooth: config.smooth,
        showSymbol: config.showSymbol,
        itemStyle: { color: COLORS.LINE },
        lineStyle: { color: COLORS.LINE },
        encode: {
          x: config.xAxis.name,
          y: config.yAxis.name,
          tooltip: [config.xAxis.name, config.yAxis.name],
        },
      },
    ],
  };
  
  // Apply user overrides last
  return deepMerge(baseOptions, userOptions);
}

/**
 * Utility to create chart options with sensible defaults and easy customization
 */
export function createChartOptions(
  xData: number[],
  yData: number[],
  partialConfig: Partial<ChartConfig> = {},
  chartOptions: Partial<EChartsOption> = {}
): EChartsOption {
  const config = createChartConfig(partialConfig, xData, yData);
  return generateEChartsOptions(xData, yData, config, chartOptions);
}

// Export constants for external use if needed
export { COLORS as CHART_COLORS };

/**
 * Generates markLines for highlighting specific data points
 */
export function createMarkLines(
  xData: number[],
  yData: number[],
  activeIndex: number | undefined,
  config: ChartConfig
): MarkLineComponentOption {
  if (activeIndex === undefined || activeIndex < 0 || activeIndex >= xData.length) {
    return {};
  }

  const x = xData[activeIndex];
  const y = yData[activeIndex];

  const markLine: MarkLineComponentOption = {
    animation: false,
    silent: true,
    lineStyle: { type: 'dashed', color: COLORS.TEXT },
    label: { show: true },
  };

  const data: NonNullable<MarkLineComponentOption['data']> = [];

  if (config.showXLine) {
    data.push([
      { coord: [x, 0] },
      { coord: [x, y], label: { formatter: `${config.yAxis.name}: ${yData[activeIndex].toFixed(2)}` } },
    ]);
  }

  if (config.showYLine) {
    data.push([
      { coord: [0, y] },
      { coord: [x, y], label: { formatter: `${config.xAxis.name}: ${xData[activeIndex].toFixed(2)}` } },
    ]);
  }

  markLine.data = data;

  return markLine;
}