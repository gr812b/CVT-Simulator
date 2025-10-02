import type { EChartsOption } from 'echarts';

/**
 * Configuration for axis display
 */
export interface AxisConfig {
  /** Display name for the axis */
  name: string;
  /** Type of axis data */
  type: 'time' | 'value' | 'category';
  /** Unit label (e.g., 'm/s', 'seconds') */
  unit?: string;
}

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
  seriesName?: string;
  /** Whether to show smooth curves */
  smooth?: boolean;
  /** Whether to show data point symbols */
  showSymbol?: boolean;
}

/**
 * Props for the Graph2D component
 */
export interface Graph2DProps {
  /** X-axis data points */
  xData: number[];
  /** Y-axis data points */
  yData: number[];
  /** Chart configuration */
  config: ChartConfig;
  /** Additional ECharts options to merge (for advanced customization) */
  chartOptions?: Partial<EChartsOption>;
  /** Class name for the container */
  className?: string;
}

/**
 * Validation result for data
 */
export interface ValidationResult {
  isValid: boolean;
  errors: string[];
  warnings: string[];
}