import { useMemo, useEffect, useRef, useCallback, memo } from 'react';
import ReactECharts from 'echarts-for-react';
import cx from 'classnames';
import styles from './Graph2D.module.scss';
import { validateData } from './validation';
import { createChartOptions, CHART_COLORS, type ChartConfig } from './chartOptions';
import { IndexOverlay } from './indexOverlay/IndexOverlay';
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
  /** Replay controller for index updates and interactions (required for functionality) */
  replayController: { 
    on: (handler: (event: { type: string; currentIndex?: number }) => void) => () => void; 
    setCurrentIndex?: (index: number) => void;
    pause?: () => void;
  };
}

function Graph2DComponent({
  xData,
  yData,
  config,
  chartOptions = {},
  className = '',
  replayController,
}: Graph2DProps) {
  const chartRef = useRef<ECharts | null>(null);
  const highlightedIndexRef = useRef<number | undefined>(undefined);
  const onChartReadyCallbackRef = useRef<((chart: ECharts) => void) | null>(null);
  const isDraggingRef = useRef<boolean>(false);

  // Validate data and generate warnings/errors
  const validation = useMemo(() => validateData(xData, yData), [xData, yData]);
  
  // Generate complete ECharts options
  const echartsOptions = useMemo(() => {
    if (!validation.isValid) {
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

  // Show warnings to user
  useEffect(() => {
    if (validation.warnings.length > 0) {
      alert('Graph warnings: ' + validation.warnings.join(', '));
    }
  }, [validation.warnings]);

  /**
   * Given a pixel X position on the zrender canvas, find the nearest data
   * index using the chart's convertFromPixel utility and clamp it to bounds.
   */
  const getIndexFromPixel = useCallback((offsetX: number): number | undefined => {
    const chart = chartRef.current;
    if (!chart || xData.length === 0) return undefined;

    const dataX = chart.convertFromPixel({ seriesIndex: 0 }, [offsetX, 0])?.[0];
    if (dataX == null) return undefined;

    // Find the nearest index via binary search for performance on large datasets
    let lo = 0;
    let hi = xData.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (xData[mid] < dataX) lo = mid + 1;
      else hi = mid;
    }
    // Check neighbour to find the truly closest point
    if (lo > 0 && Math.abs(xData[lo - 1] - dataX) < Math.abs(xData[lo] - dataX)) {
      lo = lo - 1;
    }
    return Math.max(0, Math.min(lo, xData.length - 1));
  }, [xData]);

  const commitIndex = useCallback((offsetX: number): void => {
    const index = getIndexFromPixel(offsetX);
    if (index === undefined) return;
    highlightedIndexRef.current = index;
    replayController?.pause?.();
    replayController?.setCurrentIndex?.(index);
  }, [getIndexFromPixel, replayController]);

  const handleChartReady = useCallback((chart: ECharts): void => {
    chartRef.current = chart;
    onChartReadyCallbackRef.current?.(chart);
  }, []);

  // Attach pointer event listeners to the zrender canvas
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const zr = chart.getZr();

    const onMouseDown = (e: { offsetX: number }): void => {
      isDraggingRef.current = true;
      commitIndex(e.offsetX);
    };

    const onMouseMove = (e: { offsetX: number }): void => {
      if (!isDraggingRef.current) return;
      commitIndex(e.offsetX);
    };

    const onMouseUp = (): void => {
      isDraggingRef.current = false;
    };

    zr.on('mousedown', onMouseDown);
    zr.on('mousemove', onMouseMove);
    zr.on('mouseup', onMouseUp);
    // Release drag if pointer leaves the canvas
    zr.on('globalout', onMouseUp);

    return () => {
      zr.off('mousedown', onMouseDown);
      zr.off('mousemove', onMouseMove);
      zr.off('mouseup', onMouseUp);
      zr.off('globalout', onMouseUp);
    };
  }, [commitIndex]);

  const handleTooltipUpdate = useCallback((params?: { dataIndex?: number }): void => {
    highlightedIndexRef.current = params?.dataIndex;
  }, []);

  const chartHeight = config.height ?? 600;
  const chartWidth = config.width || '100%';
  
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

        <IndexOverlay
          xData={xData}
          yData={yData}
          replayController={replayController}
          xAxis={{ label: config.xAxis.name, unit: config.xAxis.unit }}
          yAxis={{ label: config.yAxis.name, unit: config.yAxis.unit }}
          seriesNames={config.seriesNames}
          tooltipPosition={config.tooltipPosition}
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

export const Graph2D = memo(Graph2DComponent, (prev, next) => 
  prev.xData === next.xData &&
  prev.yData === next.yData &&
  prev.config === next.config &&
  prev.chartOptions === next.chartOptions &&
  prev.className === next.className &&
  prev.replayController === next.replayController
);