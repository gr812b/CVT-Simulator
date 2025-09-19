import type { EChartsOption } from 'echarts';
import type { ChartConfig, ChartTheme, DataPoint2D } from './types';
import { createDefaultConfig, createTheme, generateChartStyle } from './theme';
import { inferAxisType } from './validation';
import { LAYOUT, CHART_DEFAULTS } from './constants';

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
 * Creates a complete chart configuration by merging user config with defaults
 */
export function createChartConfig(userConfig: Partial<ChartConfig>, data: DataPoint2D[]): ChartConfig {
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
  if (data.length > 0 && !userConfig.xAxis?.type) {
    const xValues = data.map(point => point.x);
    mergedConfig.xAxis.type = inferAxisType(xValues);
  }
  
  return mergedConfig;
}

/**
 * Converts data points to ECharts dataset format
 */
export function createDataset(data: DataPoint2D[], config: ChartConfig): EChartsOption['dataset'] {
  const source: (string | number | Date)[][] = [[config.xAxis.name, config.yAxis.name]];
  data.forEach(point => source.push([point.x, point.y]));
  return { source };
}

/**
 * Generates complete ECharts options
 */
export function generateEChartsOptions(
  data: DataPoint2D[],
  config: ChartConfig,
  theme: ChartTheme = {},
  userOptions: Partial<EChartsOption> = {}
): EChartsOption {
  const finalTheme = createTheme(theme);
  const dataset = createDataset(data, config);
  
  // Base options
  const baseOptions: EChartsOption = {
    title: config.title ? {
      text: config.title,
      left: 'center',
      top: LAYOUT.TITLE.TOP,
    } : undefined,
    
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    
    toolbox: {
      feature: {
        dataZoom: { yAxisIndex: 'none' },
        restore: {},
        saveAsImage: {},
      },
      right: LAYOUT.TOOLBOX.RIGHT,
      top: LAYOUT.TOOLBOX.TOP,
    },
    
    dataset,
    
    grid: {
      left: LAYOUT.GRID.LEFT,
      right: LAYOUT.GRID.RIGHT,
      top: config.title ? LAYOUT.GRID.TOP_WITH_TITLE : LAYOUT.GRID.TOP_WITHOUT_TITLE,
      bottom: LAYOUT.GRID.BOTTOM,
      containLabel: true,
    },
    
    xAxis: {
      type: config.xAxis.type,
      name: config.xAxis.name,
      nameLocation: 'middle',
      nameGap: LAYOUT.X_AXIS_NAME_GAP,
      boundaryGap: config.xAxis.type === 'category',
      axisLabel: { hideOverlap: CHART_DEFAULTS.HIDE_OVERLAP },
    },
    
    yAxis: {
      type: config.yAxis.type,
      name: config.yAxis.name,
      nameLocation: 'middle',
      nameGap: LAYOUT.Y_AXIS_NAME_GAP,
      axisLabel: { hideOverlap: CHART_DEFAULTS.HIDE_OVERLAP },
      splitLine: { show: CHART_DEFAULTS.SHOW_SPLIT_LINES },
    },
    
    dataZoom: [
      { type: 'inside', xAxisIndex: 0 },
      { type: 'slider', xAxisIndex: 0, bottom: LAYOUT.SLIDER_BOTTOM },
    ],
    
    series: [
      {
        type: 'line',
        name: config.seriesName || `${config.yAxis.name} vs ${config.xAxis.name}`,
        smooth: config.smooth,
        showSymbol: config.showSymbol,
        itemStyle: { color: finalTheme.lineColor },
        lineStyle: { color: finalTheme.lineColor },
        encode: {
          x: config.xAxis.name,
          y: config.yAxis.name,
          tooltip: [config.xAxis.name, config.yAxis.name],
        },
      },
    ],
  };
  
  // Apply theme styling
  const styledOptions = deepMerge(baseOptions, generateChartStyle(finalTheme));
  
  // Apply user overrides last
  return deepMerge(styledOptions, userOptions);
}

/**
 * Utility to create chart options with sensible defaults and easy customization
 */
export function createChartOptions(
  data: DataPoint2D[],
  partialConfig: Partial<ChartConfig> = {},
  theme: ChartTheme = {},
  chartOptions: Partial<EChartsOption> = {}
): EChartsOption {
  const config = createChartConfig(partialConfig, data);
  return generateEChartsOptions(data, config, theme, chartOptions);
}