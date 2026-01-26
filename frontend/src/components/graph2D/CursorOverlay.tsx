import { useRef, useEffect, useCallback, useState } from 'react';
import type { ECharts } from 'echarts';
import styles from './Graph2D.module.scss';

interface CursorOverlayProps {
  xData: number[];
  yData: number[][];
  activeIndex?: number;
  replayController?: {
    on: (handler: (event: { type: string; currentIndex?: number }) => void) => () => void;
  };
  onMount?: (callback: (chart: ECharts) => void) => void;
  xAxisLabel?: string;
  yAxisLabel?: string;
  xUnit?: string;
  yUnit?: string;
  seriesNames?: string[];
}

export function CursorOverlay({
  xData,
  yData,
  activeIndex,
  replayController,
  onMount,
  xAxisLabel = 't',
  yAxisLabel = 'y',
  xUnit = '',
  yUnit = '',
  seriesNames = [],
}: CursorOverlayProps) {
  const [chart, setChart] = useState<ECharts | null>(null);
  const cursorLineRef = useRef<HTMLDivElement | null>(null);
  const cursorLabelRef = useRef<HTMLDivElement | null>(null);
  const cursorDotRef = useRef<HTMLDivElement | null>(null);
  const gridRectRef = useRef<{ x: number; y: number; width: number; height: number } | null>(null);
  const currentIndexRef = useRef<number>(activeIndex ?? 0);
  const isInitializedRef = useRef(false);

  // Register chart ready callback
  useEffect(() => {
    if (!onMount) return;
    onMount((chartInstance) => {
      setChart(chartInstance);
    });
  }, [onMount]);

  // Update grid rect when chart resizes or rerenders
  const updateGridRect = useCallback(() => {
    if (!chart) return;

    try {
      const gridComp = chart.getModel().getComponent('grid', 0);
      const rect = gridComp.coordinateSystem.getRect();

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
  }, [chart]);

  // Update cursor DOM position
  const updateCursorDom = useCallback((index: number) => {
    const lineEl = cursorLineRef.current;
    const labelEl = cursorLabelRef.current;
    const dotEl = cursorDotRef.current;

    if (!chart || !lineEl || !labelEl || !dotEl || !isInitializedRef.current) {
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

    // Position dot at first series data point
    const firstYValue = yValues[0];
    if (firstYValue != null) {
      const py = chart.convertToPixel({ yAxisIndex: 0 }, firstYValue) as number;
      const dotX = px - 6;
      const dotY = py - 6;
      dotEl.style.transform = `translate3d(${dotX}px, ${dotY}px, 0)`;
      dotEl.style.display = 'block';
    } else {
      dotEl.style.display = 'none';
    }

    // Build label with all series values
    const xLabel = xUnit ? `${xAxisLabel}: ${xValue.toFixed(2)} ${xUnit}` : `${xAxisLabel}: ${xValue.toFixed(2)}`;
    
    const yLabels = yValues.map((yValue, idx) => {
      if (yValue == null) return null;
      const name = seriesNames[idx] || `${yAxisLabel}${yValues.length > 1 ? ` ${idx + 1}` : ''}`;
      return yUnit ? `${name}: ${yValue.toFixed(2)} ${yUnit}` : `${name}: ${yValue.toFixed(2)}`;
    }).filter(Boolean);
    
    const text = yLabels.length === 0 ? xLabel : `${xLabel}, ${yLabels.join(', ')}`;

    labelEl.textContent = text;
    labelEl.style.transform = `translate3d(${rect.x}px, 10px, 0)`;
    labelEl.style.display = 'block';
  }, [chart, xData, yData, xAxisLabel, yAxisLabel, xUnit, yUnit, seriesNames]);

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

  // Update cursor when activeIndex prop changes
  useEffect(() => {
    if (activeIndex !== undefined) {
      currentIndexRef.current = activeIndex;
      updateCursorDom(activeIndex);
    }
  }, [activeIndex, updateCursorDom]);

  // Subscribe to replay controller
  useEffect(() => {
    if (!replayController) return;

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
      <div 
        ref={cursorDotRef} 
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: '12px',
          height: '12px',
          borderRadius: '50%',
          background: 'white',
          boxShadow: '0 0 0 2px black',
          zIndex: 9999,
          pointerEvents: 'none',
          willChange: 'transform',
          display: 'none'
        }}
      />
      <div ref={cursorLabelRef} className={styles.cursorLabel} />
    </div>
  );
}
