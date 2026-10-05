import { useMemo, useEffect, useRef, useState, useCallback, memo } from 'react';
import ReactECharts from 'echarts-for-react';
import { Text } from '@mantine/core';
import cx from 'classnames';
import styles from './Graph2D.module.scss';
import { validateData } from './validation';
import {
  createChartOptions,
  CHART_COLORS,
  type ChartConfig,
} from './chartOptions';
import { IndexOverlay } from './indexOverlay/IndexOverlay';
import type { ECharts, EChartsOption } from 'echarts';

/**
 * Props for the Graph2D component
 */
export type GraphViewState = {
  zoom: { start: number; end: number }[];
  selected: Record<string, boolean>;
};

export interface Graph2DProps {
  viewState?: GraphViewState;
  onViewStateChange?: (state: GraphViewState) => void;
  /** X-axis data points */
  xData: number[];
  /** Y-axis data points */
  yData: Array<Array<number | null>>;
  /** Chart configuration */
  config: ChartConfig;
  /** Additional ECharts options to merge (for advanced customization) */
  chartOptions?: Partial<EChartsOption>;
  /** Class name for the container */
  className?: string;
  /** Replay controller for index updates and interactions (required for functionality) */
  replayController: {
    on: (
      handler: (event: { type: string; currentIndex?: number }) => void,
    ) => () => void;
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
  viewState,
  onViewStateChange,
  replayController,
}: Graph2DProps) {
  const chartRef = useRef<ECharts | null>(null);
  const [readyChart, setReadyChart] = useState<ECharts | null>(null);

  // Validate data and generate warnings/errors
  const validation = useMemo(() => validateData(xData, yData), [xData, yData]);
  const orderedX = useMemo(
    () => xData.every((x, i) => i === 0 || x >= xData[i - 1]),
    [xData],
  );

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

    const options = createChartOptions(xData, yData, config, chartOptions);
    if (viewState) {
      const zooms = Array.isArray(options.dataZoom)
        ? options.dataZoom
        : options.dataZoom
          ? [options.dataZoom]
          : [];
      options.dataZoom = zooms.map((zoom, index) => ({
        ...zoom,
        ...viewState.zoom[index],
      }));
      options.legend = {
        ...(!Array.isArray(options.legend) ? options.legend : {}),
        selected: viewState.selected,
      };
    }
    return options;
  }, [xData, yData, config, chartOptions, validation, viewState]);

  const handleChartReady = useCallback((chart: ECharts): void => {
    chartRef.current = chart;
    setReadyChart(chart);
  }, []);

  useEffect(() => {
    if (!readyChart || !xData.length) return;
    const seek = (event: { offsetX: number; offsetY: number }) => {
      if (
        !readyChart.containPixel({ gridIndex: 0 }, [
          event.offsetX,
          event.offsetY,
        ])
      )
        return;
      const time = readyChart.convertFromPixel(
        { xAxisIndex: 0 },
        event.offsetX,
      ) as number;
      if (!Number.isFinite(time)) return;
      let lo = 0,
        hi = xData.length - 1;
      while (lo < hi) {
        const mid = Math.floor((lo + hi) / 2);
        if (xData[mid] < time) lo = mid + 1;
        else hi = mid;
      }
      let index =
        lo > 0 && time - xData[lo - 1] < xData[lo] - time ? lo - 1 : lo;
      if (!orderedX) {
        // Speed/force and shift-curve plots can double back. Select the nearest
        // recorded point in screen space rather than treating their X as time.
        const y = readyChart.convertFromPixel(
          { yAxisIndex: 0 },
          event.offsetY,
        ) as number;
        const dx =
          Math.abs(
            (readyChart.convertFromPixel(
              { xAxisIndex: 0 },
              event.offsetX + 1,
            ) as number) - time,
          ) || 1;
        const dy =
          Math.abs(
            (readyChart.convertFromPixel(
              { yAxisIndex: 0 },
              event.offsetY + 1,
            ) as number) - y,
          ) || 1;
        let nearest = Number.POSITIVE_INFINITY;
        yData.forEach((row, i) =>
          row.forEach((value) => {
            if (value === null) return;
            const distance =
              ((xData[i] - time) / dx) ** 2 + ((value - y) / dy) ** 2;
            if (distance < nearest) {
              nearest = distance;
              index = i;
            }
          }),
        );
      }
      replayController.pause?.();
      replayController.setCurrentIndex?.(index);
    };
    const zr = readyChart.getZr();
    zr.on('click', seek);
    return () => zr.off('click', seek);
  }, [readyChart, replayController, xData, yData, orderedX]);

  const rememberView = () => {
    const option = chartRef.current?.getOption() as
      | {
          dataZoom?: { start?: number; end?: number }[];
          legend?: { selected?: Record<string, boolean> }[];
        }
      | undefined;
    if (option)
      onViewStateChange?.({
        zoom: (option.dataZoom ?? []).map((zoom) => ({
          start: zoom.start ?? 0,
          end: zoom.end ?? 100,
        })),
        selected: option.legend?.[0]?.selected ?? {},
      });
  };

  const chartHeight = config.height ?? 600;
  const chartWidth = config.width || '100%';

  // If data is invalid, show error state
  if (!validation.isValid) {
    return (
      <div
        className={cx(styles.graph2dError, className)}
        style={{ height: chartHeight }}
      >
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
      {validation.warnings.length > 0 && (
        <Text size="xs" c="dimmed" role="status">
          {validation.warnings.join('. ')}
        </Text>
      )}
      <div className={styles.chartContainer}>
        <ReactECharts
          option={echartsOptions}
          style={{ width: chartWidth, height: chartHeight }}
          notMerge={false}
          lazyUpdate
          onChartReady={handleChartReady}
          onEvents={{
            datazoom: rememberView,
            legendselectchanged: rememberView,
            restore: () => {
              chartRef.current?.dispatchAction({
                type: 'dataZoom',
                batch: [0, 1].map((dataZoomIndex) => ({
                  dataZoomIndex,
                  start: 0,
                  end: 100,
                })),
              });
              rememberView();
            },
          }}
        />

        <IndexOverlay
          xData={xData}
          yData={yData}
          replayController={replayController}
          seriesNames={config.seriesNames}
          chart={readyChart}
        />
      </div>
    </div>
  );
}

/**
 * Memoized Graph2D - uses referential equality to avoid expensive deep equality checks
 * on large datasets. DOM-based index updates during playback bypass React entirely.
 */
export const Graph2D = memo(
  Graph2DComponent,
  (prev, next) =>
    prev.viewState === next.viewState &&
    prev.onViewStateChange === next.onViewStateChange &&
    prev.xData === next.xData &&
    prev.yData === next.yData &&
    prev.config === next.config &&
    prev.chartOptions === next.chartOptions &&
    prev.className === next.className &&
    prev.replayController === next.replayController,
);
