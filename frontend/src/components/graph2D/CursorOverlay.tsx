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
}

export function CursorOverlay({
  xData,
  yData,
  activeIndex,
  replayController,
  onMount,
}: CursorOverlayProps) {
  const [chart, setChart] = useState<ECharts | null>(null);
  const cursorLineRef = useRef<HTMLDivElement | null>(null);
  const cursorLabelRef = useRef<HTMLDivElement | null>(null);
  const gridRectRef = useRef<{ x: number; y: number; width: number; height: number } | null>(null);
  const currentIndexRef = useRef<number | undefined>(activeIndex);
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
        const isFirstUpdate = !gridRectRef.current;
        gridRectRef.current = rect;

        if (isFirstUpdate) {
          console.log('[CursorOverlay] Grid rect initialized:', rect);
        }

        // Re-render cursor if we have a pending index
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

    if (!chart || !lineEl || !labelEl || !isInitializedRef.current) {
      return;
    }

    const xValue = xData[index];
    if (xValue == null) {
      return;
    }

    const rect = gridRectRef.current;
    if (!rect) {
      if (currentIndexRef.current === undefined) {
        console.warn('[CursorOverlay] Grid rect not ready on first cursor render');
      }
      currentIndexRef.current = index;
      return;
    }

    // Convert x value to pixel coordinate
    const px = chart.convertToPixel({ xAxisIndex: 0 }, xValue) as number;

    // Position cursor line
    lineEl.style.transform = `translate3d(${px}px, ${rect.y}px, 0)`;
    lineEl.style.height = `${rect.height}px`;
    lineEl.style.display = 'block';

    // Build and position label
    const y0 = yData[0]?.[index];
    const text = y0 == null
      ? `t=${xValue.toFixed(3)}`
      : `t=${xValue.toFixed(3)}\ny=${y0.toFixed(3)}`;

    labelEl.textContent = text;
    labelEl.style.transform = `translate3d(${rect.x + 8}px, ${rect.y + 8}px, 0)`;
    labelEl.style.display = 'block';
  }, [chart, xData, yData]);

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
      <div ref={cursorLabelRef} className={styles.cursorLabel} />
    </div>
  );
}
