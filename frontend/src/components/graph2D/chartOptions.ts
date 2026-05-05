import type { 
  EChartsOption, 
  DefaultLabelFormatterCallbackParams 
} from 'echarts';
import { VALIDATION } from './validation';

/**
 * Configuration for axis display
 */
interface AxisConfig {
  /** Display name for the axis */
  name: string;
  /** Type of axis data */
  type: 'time' | 'value' | 'category';
  /** Unit label (e.g., 'm/s', 'seconds') */
  unit?: string;
}

export enum TooltipPosition {
  TopLeft = 'top-left',
  TopRight = 'top-right',
  BottomLeft = 'bottom-left',
  BottomRight = 'bottom-right',
}

export interface LinearReferenceLineConfig {
  /** Discriminator for future equation types */
  type: 'linear';
  /** Label shown in legend and tooltip */
  label: string;
  /** Slope in y = slope*x + intercept */
  slope: number;
  /** Optional y-intercept (default 0) */
  intercept?: number;
  /** Optional line color override */
  color?: string;
  /** Optional line width override */
  width?: number;
  /** Optional stroke style override */
  lineType?: 'solid' | 'dashed' | 'dotted';
}

export type ReferenceLineConfig = LinearReferenceLineConfig;

/**
 * Chart configuration options
 */
export interface ChartConfig {
  /** Title displayed above the chart */
  title?: string;
  /** Chart height in pixels */
  height?: number;
  /** Chart width (default: 100%) */
  width?: string | number;
  /** X-axis configuration */
  xAxis: AxisConfig;
  /** Y-axis configuration */
  yAxis: AxisConfig;
  /** Series name for the line */
  seriesNames?: string[];
  /** Whether to show smooth curves */
  smooth?: boolean;
  /** Whether to show data point symbols */
  showSymbol?: boolean;
  /** Whether to draw a vertical line at x[index] */
  showXLine?: boolean;
  /** Whether to draw a horizontal line at y[index] */
  showYLine?: boolean;
  /** Position of the tooltip relative to the cursor */
  tooltipPosition?: TooltipPosition;
  /** Optional reference lines drawn on top of chart data */
  referenceLines?: ReferenceLineConfig[];
}

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
  get BACKGROUND() { return getCSSColor('--background', '#222222'); },
  get TEXT() { return getCSSColor('--text-color', '#ffffff'); },
  get GRID() { return getCSSColor('--grid-color', '#404040'); },
  get LINES() {
    return [
      getCSSColor('--line1', '#bb0808'),
      getCSSColor('--line2', '#2ecc71'),
      getCSSColor('--line3', '#3498db'),
      getCSSColor('--line4', '#e67e22'),
      getCSSColor('--line5', '#9b59b6'),
      getCSSColor('--line6', '#f1c40f'),
      getCSSColor('--line7', '#00ffff'),
      getCSSColor('--line8', '#ff00ff'),
      getCSSColor('--line9', '#e74c3c'),
    ];
  },
  get PRIMARY() { return getCSSColor('--primary', '#bb0808'); },
  get TOOLTIP_BG() { return getCSSColor('--tooltip-bg', '#2a2a2a'); },
  get ZOOM_FILL() { 
    const hex = getCSSColor('--primary', '#bb0808').replace('#', '');
    const r = parseInt(hex.substring(0, 2), 16);
    const g = parseInt(hex.substring(2, 4), 16);
    const b = parseInt(hex.substring(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, 0.2)`;
  },
  get ERROR() { return getCSSColor('--error', '#c00f0c'); },
} as const;

const LAYOUT = {
  DEFAULT_HEIGHT: 400,
  DEFAULT_WIDTH: '100%',
  
  GRID: {
    LEFT: 60,
    RIGHT: 60,
    TOP_WITH_TITLE: 60,
    TOP_WITHOUT_TITLE: 40,
    BOTTOM: 70,
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
  SLIDER_RIGHT: 10,
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
 * Stable value formatter function to prevent unnecessary re-renders for tooltip
 */
const stableValueFormatter = (value: unknown): string => {
  return typeof value === 'number' ? value.toFixed(2) : String(value);
};

/**
 * Cache for memoized tooltip formatters to prevent unnecessary re-renders
 */
const tooltipFormatterCache = new Map<string, (params: DefaultLabelFormatterCallbackParams | DefaultLabelFormatterCallbackParams[]) => string>();

/**
 * Creates a tooltip formatter that includes units.
 * Returns either a string template or a stable function reference.
 */
function createTooltipFormatter(config: ChartConfig) {
  // For simple cases, we could use ECharts string templates:
  // return `${config.xAxis.name}: {c0}<br/>${config.yAxis.name}: {c1}`;
  
  // But for unit support and formatting, we need the function approach with caching
  const cacheKey = JSON.stringify({
    xAxisName: config.xAxis.name,
    yAxisName: config.yAxis.name,
    xAxisUnit: config.xAxis.unit,
    yAxisUnit: config.yAxis.unit,
    seriesNames: config.seriesNames,
  });
  
  // Return cached formatter if it exists
  if (tooltipFormatterCache.has(cacheKey)) {
    return tooltipFormatterCache.get(cacheKey)!;
  }
  
  // Create new formatter
  const formatter = (params: DefaultLabelFormatterCallbackParams | DefaultLabelFormatterCallbackParams[]) => {
    // ECharts passes either a single param object or an array of param objects
    // For 'axis' trigger (which we use), it's always an array
    const paramArray = Array.isArray(params) ? params : [params];
    
    if (paramArray.length > 0) {
      const firstParam = paramArray[0];
      const xUnit = config.xAxis.unit ? ` ${config.xAxis.unit}` : '';
      const yUnit = config.yAxis.unit ? ` ${config.yAxis.unit}` : '';

      const firstValue = Array.isArray(firstParam.value) ? firstParam.value[0] : firstParam.axisValue;
      const xLine = `${config.xAxis.name}: ${stableValueFormatter(firstValue)}${xUnit}<br/>`;

      const yLines = paramArray
        .map((param, index) => {
          const markerColor = typeof param.color === 'string'
            ? param.color
            : COLORS.LINES[index % COLORS.LINES.length];
          const marker = `<span style="
              display:inline-block;
              margin-right:6px;
              border-radius:50%;
              width:8px;
              height:8px;
              background-color:${markerColor};
          "></span>`;

          const rawValue = Array.isArray(param.value) ? param.value[1] : param.value;
          const seriesLabel = param.seriesName || config.yAxis.name;
          return `${marker} ${seriesLabel}: ${stableValueFormatter(rawValue)}${yUnit}`;
        })
        .filter(Boolean);

      return `
          ${xLine}
          ${yLines.join('<br/>')}
        `;
    }
    return '';
  };
  
  // Cache and return the formatter
  tooltipFormatterCache.set(cacheKey, formatter);
  return formatter;
}

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
export function createChartConfig(userConfig: Partial<ChartConfig>, xData: number[], yData: number[][]): ChartConfig {
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
    mergedConfig.yAxis.type = inferAxisType(yData[0]);
  }
  
  return mergedConfig;
}

/**
 * Converts data points to ECharts dataset format
 */
export function createDataset(xData: number[], yData: number[][], config: ChartConfig): EChartsOption['dataset'] {


  const source: (string | number | Date)[][] = [[config.xAxis.name]];

  const seriesCount = yData[0]?.length || 0;
  for (let i = 0; i < seriesCount; i++) {
    source[0].push(config.seriesNames?.[i] || `${config.yAxis.name} ${i + 1}`);
  }

  xData.forEach((x, index) => {
    const y = yData[index];
    source.push([x, ...y]);
  });

  return { source };
}

/**
 * Generates the series array for ECharts options
 */
function createSeries(xData: number[], yData: number[][], config: ChartConfig): EChartsOption['series'] {
  const seriesCount = yData[0]?.length || 0;
  const seriesArray: EChartsOption['series'] = [];

  for (let i = 0; i < seriesCount; i++) {
    seriesArray.push({
      type: 'line',
      progressive: 5000,
      progressiveThreshold: 10000,
      sampling: 'lttb',
      animation: false,
      symbol: 'none',
      name: config.seriesNames?.[i] || `${config.yAxis.name} ${i + 1}`,
      smooth: config.smooth,
      showSymbol: config.showSymbol,
      itemStyle: { color: COLORS.LINES[i % COLORS.LINES.length] },
      lineStyle: { color: COLORS.LINES[i % COLORS.LINES.length], width: 3 },
      encode: {
        x: config.xAxis.name,
        y: i + 1,
      },
    });
  }

  for (let i = 0; i < (config.referenceLines?.length ?? 0); i++) {
    const referenceLine = config.referenceLines![i];

    if (referenceLine.type === 'linear') {
      const intercept = referenceLine.intercept ?? 0;
      const color = referenceLine.color ?? COLORS.LINES[(seriesCount + i) % COLORS.LINES.length];

      seriesArray.push({
        type: 'line',
        animation: false,
        symbol: 'none',
        smooth: false,
        showSymbol: false,
        name: referenceLine.label,
        data: xData.map((x) => [x, referenceLine.slope * x + intercept]),
        itemStyle: { color },
        lineStyle: {
          color,
          width: referenceLine.width ?? 2,
          type: referenceLine.lineType ?? 'dashed',
        },
      });
    }
  }

  return seriesArray;
}

function getNumericBounds(values: number[]): { min: number; max: number } | null {
  const finiteValues = values.filter((value) => Number.isFinite(value));
  if (finiteValues.length === 0) {
    return null;
  }

  const min = Math.min(...finiteValues);
  const max = Math.max(...finiteValues);

  if (min === max) {
    const padding = Math.abs(min) > 0 ? Math.abs(min) * 0.05 : 1;
    return { min: min - padding, max: max + padding };
  }

  return { min, max };
}


/**
 * Generates complete ECharts options with dark theme defaults
 */
export function generateEChartsOptions(
  xData: number[],
  yData: number[][],
  config: ChartConfig,
  userOptions: Partial<EChartsOption> = {}
): EChartsOption {
  const dataset = createDataset(xData, yData, config);
  const series = createSeries(xData, yData, config);
  const hasReferenceLines = (config.referenceLines?.length ?? 0) > 0;

  const xBounds = hasReferenceLines && config.xAxis.type !== 'category'
    ? getNumericBounds(xData)
    : null;

  const yBounds = hasReferenceLines && config.yAxis.type !== 'category'
    ? getNumericBounds(yData.flatMap((point) => point))
    : null;

  // Create axis options separately to avoid type inference issues
  const xAxisOption = {
    type: config.xAxis.type,
    min: xBounds?.min,
    max: xBounds?.max,
    name: config.xAxis.unit ? `${config.xAxis.name} (${config.xAxis.unit})` : config.xAxis.name,
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
    min: yBounds?.min,
    max: yBounds?.max,
    name: config.yAxis.unit ? `${config.yAxis.name} (${config.yAxis.unit})` : config.yAxis.name,
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
    animation: false, // Disabled for performance - 20 graphs with animation kills FPS
    backgroundColor: COLORS.BACKGROUND,
    textStyle: { color: COLORS.TEXT },
    
    title: config.title ? {
      text: config.title,
      left: 'center',
      top: LAYOUT.TITLE.TOP,
      textStyle: { color: COLORS.TEXT },
    } : undefined,
    
    // TODO: Only enable if playback paused
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      backgroundColor: COLORS.TOOLTIP_BG,
      borderColor: COLORS.GRID,
      textStyle: { color: COLORS.TEXT },
      formatter: createTooltipFormatter(config),
    },
    
    // TODO: Only enable if playback paused
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
        iconStyle: { borderColor: COLORS.PRIMARY },
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
    
    // TODO: Only enable if playback paused
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
          color: COLORS.PRIMARY,
          borderColor: COLORS.PRIMARY,
        },
      },
      { 
        type: 'slider', 
        yAxisIndex: 0, 
        right: LAYOUT.SLIDER_RIGHT,
        textStyle: { color: COLORS.TEXT },
        borderColor: COLORS.GRID,
        fillerColor: COLORS.ZOOM_FILL,
        handleStyle: {
          color: COLORS.PRIMARY,
          borderColor: COLORS.PRIMARY,
        },
      },
    ],
    
    series: series
  };
  
  // Apply user overrides last
  return deepMerge(baseOptions, userOptions);
}

/**
 * Utility to create chart options with sensible defaults and easy customization
 */
export function createChartOptions(
  xData: number[],
  yData: number[][],
  partialConfig: Partial<ChartConfig> = {},
  chartOptions: Partial<EChartsOption> = {}
): EChartsOption {
  const config = createChartConfig(partialConfig, xData, yData);
  return generateEChartsOptions(xData, yData, config, chartOptions);
}

// Export constants for external use if needed
export { COLORS as CHART_COLORS };

/**
 * Determines the appropriate axis type based on data
 */
export function inferAxisType(values: (number | string | Date)[]): 'time' | 'value' | 'category' {
  if (values.length === 0) return 'category';
  
  // Check if all values are numbers
  const numericCount = values.filter(v => typeof v === 'number' && Number.isFinite(v)).length;
  if (numericCount === values.length) {
    return 'value';
  }
  
  // Check if values are dates or date-like strings
  const dateCount = values.filter(v => {
    if (v instanceof Date) return true;
    if (typeof v === 'string') {
      const parsed = Date.parse(v);
      return Number.isFinite(parsed);
    }
    return false;
  }).length;
  
  const threshold = Math.max(1, Math.floor(values.length * VALIDATION.DATE_DETECTION_THRESHOLD));
  if (dateCount >= threshold) {
    return 'time';
  }
  
  return 'category';
}