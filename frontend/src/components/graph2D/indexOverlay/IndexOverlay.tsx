import { useRef, useEffect, useCallback, useState } from 'react';
import type { ECharts, EChartsOption } from 'echarts';
import styles from './IndexOverlay.module.scss';
import { ReplayEventType } from '@utils/ReplayController';

interface AxisConfig {
  label: string;
  unit?: string;
}

interface IndexOverlayProps {
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

export function IndexOverlay({
  xData,
  yData,
  replayController,
  onMount,
  xAxis,
  yAxis,
  seriesNames = [],
}: IndexOverlayProps) {
  const [chart, setChart] = useState<ECharts | null>(null);
  const indexLineRef = useRef<HTMLDivElement | null>(null);
  const indexTooltipRef = useRef<HTMLDivElement | null>(null);
  const indexDotsRef = useRef<HTMLDivElement[]>([]);
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

  // Update index DOM position
  const updateIndexDom = useCallback((index: number) => {
    const lineEl = indexLineRef.current;
    const tooltipEl = indexTooltipRef.current;
    const dotEls = indexDotsRef.current;

    if (!chart || !lineEl || !tooltipEl || !isInitializedRef.current) {
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

    // Position index line
    lineEl.style.transform = `translate3d(${px}px, ${rect.y}px, 0)`;
    lineEl.style.height = `${rect.height}px`;
    lineEl.style.display = 'block';

    // Position dots for each series data point
    yValues.forEach((yValue, seriesIndex) => {
      const dotEl = dotEls[seriesIndex];
      if (!dotEl) return;

      if (yValue != null) {
        const py = chart.convertToPixel({ yAxisIndex: 0 }, yValue) as number;
        dotEl.style.transform = `translate3d(${px - 6}px, ${py - 6}px, 0)`;
        dotEl.style.display = 'block';
      } else {
        dotEl.style.display = 'none';
      }
    });

    // Hide unused dots
    for (let i = yValues.length; i < dotEls.length; i++) {
      if (dotEls[i]) dotEls[i].style.display = 'none';
    }

    // Build tooltip HTML
    const xLabel = xAxis.unit
      ? `${xAxis.label}: ${xValue.toFixed(2)} ${xAxis.unit}`
      : `${xAxis.label}: ${xValue.toFixed(2)}`;

    const yLines = yValues
      .map((yValue, idx) => {
        if (yValue == null) return '';
        const name = seriesNames[idx] || `${yAxis.label}${yValues.length > 1 ? ` ${idx + 1}` : ''}`;
        const color = `var(--line${idx + 1}, #ffffff)`;
        const val = yAxis.unit ? `${yValue.toFixed(2)} ${yAxis.unit}` : yValue.toFixed(2);
        return `<div style="display:flex;align-items:center;gap:6px;">
          <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};flex-shrink:0;"></span>
          <span>${name}: ${val}</span>
        </div>`;
      })
      .filter(Boolean);

    tooltipEl.innerHTML = `<div>${xLabel}</div>${yLines.join('')}`;

    // Use convertToPixel to get the true top-left corner of the plot area.
    // This is accurate regardless of how grid margins are specified (string, percent,
    // or number) and stays correct during data zoom.
    const gridOrigin = chart.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [xData[0], 0]) as [number, number];
    const option = chart.getOption() as EChartsOption & { yAxis: { max?: number }[] };
    const yMax = option.yAxis?.[0]?.max;
    const gridTop = yMax != null
      ? (chart.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [xData[0], yMax]) as [number, number])[1]
      : rect.y;

    tooltipEl.style.left = `${gridOrigin[0] + 8}px`;
    tooltipEl.style.top = `${gridTop + 8}px`;
    tooltipEl.style.display = 'block';
  }, [chart, xData, yData, xAxis, yAxis, seriesNames]);

  // Update grid rect when chart resizes or rerenders
  const updateGridRect = useCallback(() => {
    if (!chart) return;

    try {
      const width = chart.getWidth();
      const height = chart.getHeight();
      const option = chart.getOption() as EChartsOption;
      const gridOption = option.grid;
      const grid = (Array.isArray(gridOption) ? gridOption[0] : gridOption) || {};

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

      if (typeof rect.x === 'number' && typeof rect.width === 'number') {
        gridRectRef.current = rect;
        if (currentIndexRef.current !== undefined && isInitializedRef.current) {
          updateIndexDom(currentIndexRef.current);
        }
      }
    } catch {
      // Grid not ready yet
    }
  }, [chart, updateIndexDom]);

  // Initialize when chart becomes available
  useEffect(() => {
    if (!chart) return;

    chart.on('finished', updateGridRect);

    requestAnimationFrame(() => {
      isInitializedRef.current = true;
      chart.resize();
    });

    return () => {
      chart.off('finished', updateGridRect);
    };
  }, [chart, updateGridRect]);

  // Subscribe to replay controller for index updates
  useEffect(() => {
    const cleanup = replayController.on((event) => {
      if (event.type === ReplayEventType.Progress && event.currentIndex !== undefined) {
        currentIndexRef.current = event.currentIndex;
        updateIndexDom(event.currentIndex);
      }
    });

    return cleanup;
  }, [replayController, updateIndexDom]);

  return (
    <div className={styles.indexOverlay}>
      <div ref={indexLineRef} className={styles.indexLine} />
      {yData[0]?.map((_, seriesIndex) => (
        <div
          key={seriesIndex}
          ref={(el) => {
            if (el) indexDotsRef.current[seriesIndex] = el;
          }}
          className={styles.indexDot}
          data-series-index={seriesIndex}
        />
      ))}
      <div ref={indexTooltipRef} className={styles.indexTooltip} />
    </div>
  );
}