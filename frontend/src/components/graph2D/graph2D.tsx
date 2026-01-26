import { useMemo, useEffect, useRef, useCallback, memo } from 'react';
import ReactECharts from 'echarts-for-react';
import cx from 'classnames';
import styles from './Graph2D.module.scss';
import { validateData } from './validation';
import { createChartOptions, CHART_COLORS, type ChartConfig } from './chartOptions';
import { CursorOverlay } from './CursorOverlay';
import type { ECharts, EChartsOption } from 'echarts';


/**
 * Props for the Graph2D component
 */
export interface Graph2DProps {
  /** X-axis data points */
  xData: number[];
  /** Y-axis data points */
  yData: number[][];
  /** Chart configuration */
  config: ChartConfig;
  /** Additional ECharts options to merge (for advanced customization) */
  chartOptions?: Partial<EChartsOption>;
  /** Class name for the container */
  className?: string;
  /** Current active index for cursor position */
  activeIndex?: number;
  /** Replay controller to subscribe to for activeIndex updates (required for functionality) */
  replayController?: { on: (handler: (event: { type: string; currentIndex?: number }) => void) => () => void; setCurrentIndex?: (index: number) => void };
}

function Graph2DComponent({
  xData,
  yData,
  config,
  chartOptions = {},
  className = '',
  activeIndex,
  replayController,
}: Graph2DProps) {
  const chartRef = useRef<ECharts | null>(null);
  const highlightedIndexRef = useRef<number | undefined>(undefined);
  const onChartReadyCallbackRef = useRef<((chart: ECharts) => void) | null>(null);

  // Validate data and generate warnings/errors
  const validation = useMemo(() => validateData(xData, yData), [xData, yData]);
  
  // Generate complete ECharts options
  const echartsOptions = useMemo(() => {
    if (!validation.isValid) {
      // Return minimal options for error state
      return {
        title: {
          text: 'No Data',
          left: 'center',
          textStyle: { color: CHART_COLORS.ERROR },
        },
      };
    }

    return createChartOptions(xData, yData, config, chartOptions);
  }, [xData, yData, config, chartOptions, validation]);

  // Log warnings to console (can be disabled in production)
  useEffect(() => {
    if (validation.warnings.length > 0) {
      console.warn('Graph2D warnings:', validation.warnings);
    }
  }, [validation.warnings]);



  // Chart interaction handlers
  const handleClick = useCallback((): void => {
    if (highlightedIndexRef.current === undefined) return;
    replayController?.setCurrentIndex?.(highlightedIndexRef.current);
  }, [replayController]);

  const handleTooltipUpdate = useCallback((params?: { dataIndex?: number }): void => {
    highlightedIndexRef.current = params?.dataIndex;
  }, []);

  const handleChartReady = useCallback((chart: ECharts): void => {
    chartRef.current = chart;
    onChartReadyCallbackRef.current?.(chart);
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const zr = chart.getZr();
    zr.on('click', handleClick);
    return () => zr.off('click', handleClick);
  }, [handleClick]);

  const chartHeight = config.height ?? 600;
  const chartWidth = config.width || '100%';
  
  // If data is invalid, show error state
  if (!validation.isValid) {
    return (
      <div className={cx(styles.graph2dError, className)} style={{ height: chartHeight }}>
        <div className={styles.errorMessage}>
          <h3>Invalid Data</h3>
          <ul>
            {validation.errors.map((error, index) => (
              <li key={index}>{error}</li>
            ))}
          </ul>
        </div>
      </div>
    );
  }
  
  return (
    <div className={cx(styles.graph2d, className)}>
      <div className={styles.chartContainer}>
        <ReactECharts
          option={echartsOptions}
          style={{ width: chartWidth, height: chartHeight }}
          notMerge={false}
          lazyUpdate
          onChartReady={handleChartReady}
          onEvents={{
            updateAxisPointer: (params: { dataIndex?: number }) => {
              handleTooltipUpdate(params);
            },
          }}
        />

        <CursorOverlay
          xData={xData}
          yData={yData}
          activeIndex={activeIndex}
          replayController={replayController}
          xAxisLabel={config.xAxis.name}
          yAxisLabel={config.yAxis.name}
          xUnit={config.xAxis.unit}
          yUnit={config.yAxis.unit}
          seriesNames={config.seriesNames}
          onMount={(callback) => {
            onChartReadyCallbackRef.current = callback;
            if (chartRef.current) {
              callback(chartRef.current);
            }
          }}
        />
      </div>
    </div>
  );
}

/**
 * Memoized Graph2D - uses referential equality to avoid expensive deep equality checks
 * on large datasets. DOM-based cursor updates during playback bypass React entirely.
 */
export const Graph2D = memo(Graph2DComponent, (prev, next) => 
  prev.xData === next.xData &&
  prev.yData === next.yData &&
  prev.config === next.config &&
  prev.chartOptions === next.chartOptions &&
  prev.className === next.className &&
  prev.activeIndex === next.activeIndex &&
  prev.replayController === next.replayController
);
