import { useMemo, useEffect, useRef, useCallback, memo } from 'react';
import ReactECharts from 'echarts-for-react';
import cx from 'classnames';
import styles from './Graph2D.module.scss';
import { validateData } from './validation';
import { createChartOptions, CHART_COLORS, type ChartConfig } from './chartOptions';
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
  const isInitialized = useRef(false);
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const cursorLineRef = useRef<HTMLDivElement | null>(null);
  const cursorLabelRef = useRef<HTMLDivElement | null>(null);

  // cache grid rect so we don't call getModel() every frame
  const gridRectRef = useRef<{ x: number; y: number; width: number; height: number } | null>(null);
  
  // Store current index so we can re-render cursor when grid rect becomes available
  const currentIndexRef = useRef<number | undefined>(activeIndex);

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

  // Shared function to update cursor DOM
  const updateCursorDom = useCallback((index: number) => {
    const chart = chartRef.current;
    const lineEl = cursorLineRef.current;
    const labelEl = cursorLabelRef.current;
    
    if (!chart || !lineEl || !labelEl || !isInitialized.current) {
      return;
    }

    const xValue = xData[index];
    if (xValue == null) {
      return;
    }

    const rect = gridRectRef.current;
    if (!rect) {
      // Grid not ready yet, store index and wait
      if (currentIndexRef.current === undefined) {
        console.warn('[Graph2D] Grid rect not ready on first cursor render');
      }
      currentIndexRef.current = index;
      return;
    }

    // Convert x value -> pixel coordinate
    const px = chart.convertToPixel({ xAxisIndex: 0 }, xValue) as number;

    // Move the cursor line using transform
    lineEl.style.transform = `translate3d(${px}px, ${rect.y}px, 0)`;
    lineEl.style.height = `${rect.height}px`;
    lineEl.style.display = 'block';

    // Build label text
    const y0 = yData[0]?.[index];
    const text = y0 == null
      ? `t=${xValue.toFixed(3)}`
      : `t=${xValue.toFixed(3)}\ny=${y0.toFixed(3)}`;

    labelEl.textContent = text;
    labelEl.style.transform = `translate3d(${rect.x + 8}px, ${rect.y + 8}px, 0)`;
    labelEl.style.display = 'block';
  }, [xData, yData]);

  // Update cursor when activeIndex prop changes (includes initial render)
  useEffect(() => {
    if (activeIndex !== undefined && validation.isValid) {
      currentIndexRef.current = activeIndex;
      updateCursorDom(activeIndex);
    }
  }, [activeIndex, validation.isValid, updateCursorDom]);

  // Subscribe to replay controller for activeIndex updates (DOM-based, no re-renders)
  useEffect(() => {
    if (!replayController || !validation.isValid) return;

    const cleanup = replayController.on((event) => {
      if (event.type === 'progress' && event.currentIndex !== undefined) {
        currentIndexRef.current = event.currentIndex;
        updateCursorDom(event.currentIndex);
      }
    });

    return cleanup;
  }, [replayController, validation.isValid, updateCursorDom]);

  const highlightedIndexRef = useRef<number | undefined>(undefined);

  /**
   * Handler for click event - updates the replay controller's current index
   */
  const handleClick = useCallback((): void => {
    if (highlightedIndexRef.current === undefined) return;
    replayController?.setCurrentIndex?.(highlightedIndexRef.current);
  }, [replayController]);

  /**
   * Listener for tooltip-highlighted point tracking
   */
  function handleTooltipUpdate(params?: { dataIndex?: number }): void {
    highlightedIndexRef.current = params?.dataIndex;
  }

  /**
   * Handle chart ready event
   */
  const handleChartReady = useCallback((chart: ECharts): void => {
    console.log('[Graph2D] Chart ready');
    chartRef.current = chart;

    const updateGridRect = () => {
      try {
        const gridComp = chart.getModel().getComponent('grid', 0);
        const rect = gridComp.coordinateSystem.getRect();
        
        // Only update if we got a valid rect - don't clear existing rect on failure
        if (rect && typeof rect.x === 'number' && typeof rect.width === 'number') {
          const isFirstUpdate = !gridRectRef.current;
          gridRectRef.current = rect;
          
          if (isFirstUpdate) {
            console.log('[Graph2D] Grid rect initialized:', rect);
          }
          
          // If we have a pending index, re-render the cursor now that grid is ready
          if (currentIndexRef.current !== undefined && isInitialized.current) {
            updateCursorDom(currentIndexRef.current);
          }
        }
      } catch {
        // Keep existing grid rect if update fails - don't set to null
      }
    };

    // update after ECharts finishes any render (including resizes)
    chart.on('finished', updateGridRect);
    
    // Mark as initialized AFTER refs are committed (next tick)
    setTimeout(() => {
      isInitialized.current = true;
      // Force chart to render by triggering resize, which will fire 'finished' event
      // DO NOT REMOVE! THIS IS IMPORTANT!
      chart.resize();
    }, 0);
  }, [updateCursorDom]);

  /**
   * Use effect to clean up event listener on unmount
   */
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const zr = chart.getZr();
    zr.on('click', handleClick);

    return () => {
      zr.off('click', handleClick);
    };
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

        {/* DOM overlay: does NOT touch ECharts rendering */}
        <div ref={overlayRef} className={styles.cursorOverlay}>
          <div ref={cursorLineRef} className={styles.cursorLine} />
          <div ref={cursorLabelRef} className={styles.cursorLabel} />
        </div>
      </div>
    </div>
  );
}

/**
 * Memoized Graph2D component that prevents expensive re-renders.
 * Uses referential equality for arrays (which are memoized in parent).
 * When replayController is provided, activeIndex updates bypass React entirely
 * via direct ECharts API calls, preventing any re-renders during playback.
 */
export const Graph2D = memo(Graph2DComponent, (prevProps, nextProps) => {
  // Use referential equality for arrays since they're memoized in the parent
  // This avoids expensive deep equality checks on potentially large datasets
  return (
    prevProps.xData === nextProps.xData &&
    prevProps.yData === nextProps.yData &&
    prevProps.config === nextProps.config &&
    prevProps.chartOptions === nextProps.chartOptions &&
    prevProps.className === nextProps.className &&
    prevProps.activeIndex === nextProps.activeIndex &&
    prevProps.replayController === nextProps.replayController
  );
});
