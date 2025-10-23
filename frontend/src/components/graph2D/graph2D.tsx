import { useMemo, useEffect, useRef } from 'react';
import ReactECharts from 'echarts-for-react';
import cx from 'classnames';
import styles from './Graph2D.module.scss';
import { validateData } from './validation';
import { createChartOptions, createMarkLines, CHART_COLORS, createActiveIndexLabel, type ChartConfig } from './chartOptions';
import type { ECharts, EChartsOption } from 'echarts';


/**
 * Props for the Graph2D component
 */
export interface Graph2DProps {
  /** X-axis data points */
  xData: number[];
  /** Y-axis data points */
  yData: number[][];
  /** Index of point to highlight on chart */
  activeIndex?: number;
  /** Function to update the active index */
  setActiveIndex?: (index: number) => void;
  /** Chart configuration */
  config: ChartConfig;
  /** Additional ECharts options to merge (for advanced customization) */
  chartOptions?: Partial<EChartsOption>;
  /** Class name for the container */
  className?: string;
}

export function Graph2D({
  xData,
  yData,
  activeIndex,
  setActiveIndex,
  config,
  chartOptions = {},
  className = '',
}: Graph2DProps) {
  const chartRef = useRef<ECharts | null>(null);

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

  // Update markLines when activeIndex changes
  useEffect(() => {
    if (!chartRef.current || !validation.isValid) return;

    const markLine = createMarkLines(xData, yData, activeIndex, config);
    const graphic = createActiveIndexLabel(xData, yData, activeIndex, config);
    
    chartRef.current.setOption({
      series: [{ markLine }],
      graphic,
    });
  }, [xData, yData, activeIndex, config, validation.isValid]);


  // const [highlightedIndex, setHighlightedIndex] = useState<number | null>(null);

  /**
   * Unified handler for click or drag-end events.
   */
  function handlePointSelect(params?: { componentType: string; dataIndex?: number }): void {
    let dataIndex: number | undefined = undefined;

    // Case 1: Direct click on data point
    if (params?.componentType === 'series') {
      dataIndex = params.dataIndex;
    }

    // // Case 2: Click/drag near a tooltip-highlighted point
    // else if (highlightedIndex !== null) {
    //   dataIndex = highlightedIndex;
    // }

    setActiveIndex?.(dataIndex || -1);
  }

  // /**
  //  * Listener for tooltip-highlighted point tracking.
  //  */
  // function handleTooltipHighlight(event: { axesInfo?: Array<{ value: number }> }): void {
  //   if (event.axesInfo && event.axesInfo.length > 0) {
  //     const axisValue = event.axesInfo[0].value;
  //     const idx = xData.findIndex((x) => x === axisValue);
  //     setHighlightedIndex(idx !== -1 ? idx : null);
  //   }
  // }

  /**
   * Setup mouse drag handlers (mousedown, mouseup, move)
   */
  // function setupDragHandlers(): void {
  //   let isDragging = false;
  //   let dragMoved = false;
  //   const chart = chartRef.current;
  //   if (!chart) return;

  //   chart.getZr().on('mousedown', () => {
  //     isDragging = true;
  //     dragMoved = false;
  //   });

  //   chart.getZr().on('mousemove', () => {
  //     if (isDragging) dragMoved = true;
  //   });

  //   chart.getZr().on('mouseup', () => {
  //     if (isDragging) {
  //       isDragging = false;

  //       // If user moved the mouse while dragging
  //       if (dragMoved && highlightedIndex !== null) {
  //         handlePointSelect();
  //       }
  //     }
  //   });
  // }

  const chartHeight = config.height || 400;
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
          notMerge
          lazyUpdate
          onChartReady={(chart) => {
            chartRef.current = chart;
            // setupDragHandlers();
            // chart.on('updateAxisPointer', handleTooltipHighlight);
          }}
          onEvents={{
            click: (params: { componentType: string; dataIndex?: number }) => {
              handlePointSelect(params);
            },
          }}
        />
      </div>
    </div>
  );
}
