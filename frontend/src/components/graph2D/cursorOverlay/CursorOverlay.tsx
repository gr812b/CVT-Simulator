import { useRef, useEffect, useCallback, useState } from 'react';
import type { ECharts, EChartsOption } from 'echarts';
import styles from './CursorOverlay.module.scss';

interface AxisConfig {
  label: string;
  unit?: string;
}

interface CursorOverlayProps {
  xData: number[];
  yData: number[][];
  replayController: {
    on: (handler: (event: { type: string; currentIndex?: number }) => void) => () => void;
  };
  onMount?: (callback: (chart: ECharts) => void) => void;
  xAxis: AxisConfig;
  yAxis: AxisConfig;
  seriesNames?: string[];
}

export function CursorOverlay({
  xData,
  yData,
  replayController,
  onMount,
  xAxis,
  yAxis,
  seriesNames = [],
}: CursorOverlayProps) {
  const [chart, setChart] = useState<ECharts | null>(null);
  const cursorLineRef = useRef<HTMLDivElement | null>(null);
  const cursorLabelRef = useRef<HTMLDivElement | null>(null);
  const cursorDotsRef = useRef<HTMLDivElement[]>([]);
  const gridRectRef = useRef<{ x: number; y: number; width: number; height: number } | null>(null);
  const currentIndexRef = useRef<number>(0);
  const isInitializedRef = useRef(false);

  // Register chart ready callback
  useEffect(() => {
    if (!onMount) return;
    onMount((chartInstance) => {
      setChart(chartInstance);
    });
  }, [onMount]);

  // Update cursor DOM position
  const updateCursorDom = useCallback((index: number) => {
    const lineEl = cursorLineRef.current;
    const labelEl = cursorLabelRef.current;
    const dotEls = cursorDotsRef.current;

    if (!chart || !lineEl || !labelEl || !isInitializedRef.current) {
      return;
    }

    const xValue = xData[index];
    const yValues = yData[index] || [];
    
    if (xValue == null) {
      return;
    }

    const rect = gridRectRef.current;
    if (!rect) {
      currentIndexRef.current = index;
      return;
    }

    // Convert x value to pixel coordinate
    const px = chart.convertToPixel({ xAxisIndex: 0 }, xValue) as number;

    // Position cursor line
    lineEl.style.transform = `translate3d(${px}px, ${rect.y}px, 0)`;
    lineEl.style.height = `${rect.height}px`;
    lineEl.style.display = 'block';

    // Position dots for each series data point
    yValues.forEach((yValue, seriesIndex) => {
      const dotEl = dotEls[seriesIndex];
      if (!dotEl) return;

      if (yValue != null) {
        const py = chart.convertToPixel({ yAxisIndex: 0 }, yValue) as number;
        const dotX = px - 6;
        const dotY = py - 6;
        dotEl.style.transform = `translate3d(${dotX}px, ${dotY}px, 0)`;
        dotEl.style.display = 'block';
      } else {
        dotEl.style.display = 'none';
      }
    });

    // Hide unused dots if we have fewer series than dot elements
    for (let i = yValues.length; i < dotEls.length; i++) {
      if (dotEls[i]) {
        dotEls[i].style.display = 'none';
      }
    }

    // Build label with all series values
    const xLabel = xAxis.unit 
      ? `${xAxis.label}: ${xValue.toFixed(2)} ${xAxis.unit}` 
      : `${xAxis.label}: ${xValue.toFixed(2)}`;
    
    const yLabels = yValues.map((yValue, idx) => {
      if (yValue == null) return null;
      const name = seriesNames[idx] || `${yAxis.label}${yValues.length > 1 ? ` ${idx + 1}` : ''}`;
      return yAxis.unit 
        ? `${name}: ${yValue.toFixed(2)} ${yAxis.unit}` 
        : `${name}: ${yValue.toFixed(2)}`;
    }).filter(Boolean);
    
    const text = yLabels.length === 0 ? xLabel : `${xLabel}, ${yLabels.join(', ')}`;

    labelEl.textContent = text;
    labelEl.style.transform = `translate3d(${rect.x}px, 10px, 0)`;
    labelEl.style.display = 'block';
  }, [chart, xData, yData, xAxis, yAxis, seriesNames]);

  // Update grid rect when chart resizes or rerenders
  const updateGridRect = useCallback(() => {
    if (!chart) return;

    try {
      // Use public API to get grid dimensions
      const width = chart.getWidth();
      const height = chart.getHeight();
      const option = chart.getOption() as EChartsOption;
      const gridOption = option.grid;
      const grid = (Array.isArray(gridOption) ? gridOption[0] : gridOption) || {};
      
      // Calculate grid rect from option values (with defaults)
      const left = typeof grid.left === 'number' ? grid.left : 60;
      const right = typeof grid.right === 'number' ? grid.right : 20;
      const top = typeof grid.top === 'number' ? grid.top : 60;
      const bottom = typeof grid.bottom === 'number' ? grid.bottom : 60;
      
      const rect = {
        x: left,
        y: top,
        width: width - left - right,
        height: height - top - bottom,
      };

      if (rect && typeof rect.x === 'number' && typeof rect.width === 'number') {
        gridRectRef.current = rect;

        // Re-render cursor with current index (defaults to 0)
        if (currentIndexRef.current !== undefined && isInitializedRef.current) {
          updateCursorDom(currentIndexRef.current);
        }
      }
    } catch {
      // Grid not ready yet
    }
  }, [chart, updateCursorDom]);

  // Initialize when chart becomes available
  useEffect(() => {
    if (!chart) return;

    chart.on('finished', updateGridRect);

    requestAnimationFrame(() => {
      isInitializedRef.current = true;
      chart.resize(); // Triggers 'finished' event
    });

    return () => {
      chart.off('finished', updateGridRect);
    };
  }, [chart, updateGridRect]);

  // Subscribe to replay controller for index updates
  useEffect(() => {

    const cleanup = replayController.on((event) => {
      if (event.type === 'progress' && event.currentIndex !== undefined) {
        currentIndexRef.current = event.currentIndex;
        updateCursorDom(event.currentIndex);
      }
    });

    return cleanup;
  }, [replayController, updateCursorDom]);

  return (
    <div className={styles.cursorOverlay}>
      <div ref={cursorLineRef} className={styles.cursorLine} />
      {yData[0]?.map((_, seriesIndex) => (
        <div
          key={seriesIndex}
          ref={(el) => {
            if (el) cursorDotsRef.current[seriesIndex] = el;
          }}
          className={styles.cursorDot}
          data-series-index={seriesIndex}
        />
      ))}
      <div ref={cursorLabelRef} className={styles.cursorLabel} />
    </div>
  );
}
