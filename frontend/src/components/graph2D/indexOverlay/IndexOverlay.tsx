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
  tooltipPadding?: number;
}

const DEFAULT_TOOLTIP_PADDING = 8;

export function IndexOverlay({
  xData,
  yData,
  replayController,
  onMount,
  xAxis,
  yAxis,
  seriesNames = [],
  tooltipPadding,
}: IndexOverlayProps) {
  const [chart, setChart] = useState<ECharts | null>(null);
  const indexLineRef = useRef<HTMLDivElement | null>(null);
  const indexTooltipRef = useRef<HTMLDivElement | null>(null);
  const indexDotsRef = useRef<HTMLDivElement[]>([]);

  // Cached grid state — only recomputed on resize/zoom/finish.
  // Computed using convertToPixel so it correctly accounts for axis label
  // width changes and data-zoom, matching the same approach as the line/dot positioning.
  const gridRectRef = useRef<{ x: number; y: number; width: number; height: number } | null>(null);

  // Current free-drop position of the tooltip in overlay-local px (left/top).
  // null means "not yet placed" — tooltip will be positioned at top-left corner of grid on first show.
  const tooltipPosRef = useRef<{ left: number; top: number } | null>(null);

  const currentIndexRef = useRef<number>(0);
  const isInitializedRef = useRef(false);

  // Stable refs for props read inside hot callbacks
  const xDataRef = useRef(xData);
  const yDataRef = useRef(yData);
  const xAxisRef = useRef(xAxis);
  const yAxisRef = useRef(yAxis);
  const seriesNamesRef = useRef(seriesNames);
  xDataRef.current = xData;
  yDataRef.current = yData;
  xAxisRef.current = xAxis;
  yAxisRef.current = yAxis;
  seriesNamesRef.current = seriesNames;

  const tooltipPaddingRef = useRef<number>(DEFAULT_TOOLTIP_PADDING);
  tooltipPaddingRef.current = tooltipPadding ?? DEFAULT_TOOLTIP_PADDING;

  // Register chart ready callback
  useEffect(() => {
    if (!onMount) return;
    onMount((chartInstance) => {
      setChart(chartInstance);
    });
  }, [onMount]);

  // ---------------------------------------------------------------------------
  // Grid rect — derived via convertToPixel so axis-label width and data-zoom
  // are automatically accounted for, consistent with how the line/dots are placed.
  // ---------------------------------------------------------------------------
  const computeGridRect = useCallback(
    (chartInstance: ECharts): { x: number; y: number; width: number; height: number } | null => {
      try {
        const xData = xDataRef.current;
        const option = chartInstance.getOption() as EChartsOption & { yAxis: { max?: number }[] };
        const yMax = option.yAxis?.[0]?.max;

        // Left edge: pixel x for the first x data point
        const gridLeft = (
          chartInstance.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [xData[0], 0]) as [number, number]
        )[0];

        // Right edge: pixel x for the last x data point
        const gridRight = (
          chartInstance.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [xData[xData.length - 1], 0]) as [number, number]
        )[0];

        // Top edge: pixel y for yMax (or fall back to option grid.top)
        const gridTop =
          yMax != null
            ? (chartInstance.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [xData[0], yMax]) as [number, number])[1]
            : (() => {
                const gridOption = (option.grid as EChartsOption['grid'] | undefined);
                const g = (Array.isArray(gridOption) ? gridOption[0] : gridOption) || {};
                return typeof (g as { top?: number }).top === 'number' ? (g as { top?: number }).top! : 60;
              })();

        // Bottom edge: pixel y for y=0
        const gridBottom = (
          chartInstance.convertToPixel({ xAxisIndex: 0, yAxisIndex: 0 }, [xData[0], 0]) as [number, number]
        )[1];

        return {
          x: gridLeft,
          y: gridTop,
          width: gridRight - gridLeft,
          height: gridBottom - gridTop,
        };
      } catch {
        return null;
      }
    },
    [],
  );

  // ---------------------------------------------------------------------------
  // Clamping — keeps tooltip inside grid + padding after any position change
  // or tooltip resize.
  // ---------------------------------------------------------------------------
  const clampTooltipPosition = useCallback(
    (
      pos: { left: number; top: number },
      tooltipW: number,
      tooltipH: number,
    ): { left: number; top: number } => {
      const rect = gridRectRef.current;
      if (!rect) return pos;

      const pad = tooltipPaddingRef.current;
      const minLeft = rect.x + pad;
      const maxLeft = rect.x + rect.width - tooltipW - pad;
      const minTop = rect.y + pad;
      const maxTop = rect.y + rect.height - tooltipH - pad;

      return {
        left: Math.min(Math.max(pos.left, minLeft), Math.max(minLeft, maxLeft)),
        top: Math.min(Math.max(pos.top, minTop), Math.max(minTop, maxTop)),
      };
    },
    [],
  );

  const applyTooltipPosition = useCallback(
    (el: HTMLDivElement, pos: { left: number; top: number }) => {
      el.style.left = `${pos.left}px`;
      el.style.top = `${pos.top}px`;
      el.style.right = '';
      el.style.bottom = '';
    },
    [],
  );

  // ---------------------------------------------------------------------------
  // Default placement — top-left corner of grid (respecting padding).
  // Called the first time the tooltip becomes visible.
  // ---------------------------------------------------------------------------
  const defaultTooltipPosition = useCallback((): { left: number; top: number } | null => {
    const rect = gridRectRef.current;
    if (!rect) return null;
    const pad = tooltipPaddingRef.current;
    return { left: rect.x + pad, top: rect.y + pad };
  }, []);

  // ---------------------------------------------------------------------------
  // ResizeObserver — clamps tooltip back into bounds whenever its size changes
  // (e.g. content updates cause it to grow).
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const tooltipEl = indexTooltipRef.current;
    if (!tooltipEl) return;

    const observer = new ResizeObserver(() => {
      const pos = tooltipPosRef.current;
      if (!pos) return;

      const clamped = clampTooltipPosition(pos, tooltipEl.offsetWidth, tooltipEl.offsetHeight);
      // Only write to DOM if the position actually changed to avoid jitter
      if (clamped.left !== pos.left || clamped.top !== pos.top) {
        tooltipPosRef.current = clamped;
        applyTooltipPosition(tooltipEl, clamped);
      }
    });

    observer.observe(tooltipEl);
    return () => observer.disconnect();
  }, [clampTooltipPosition, applyTooltipPosition]);

  // ---------------------------------------------------------------------------
  // Drag logic — free movement, clamped to grid + padding
  // ---------------------------------------------------------------------------
  const dragStateRef = useRef<{
    dragging: boolean;
    startMouseX: number;
    startMouseY: number;
    startLeft: number;
    startTop: number;
  } | null>(null);

  const setupDrag = useCallback(
    (tooltipEl: HTMLDivElement) => {
      const onMouseDown = (e: MouseEvent) => {
        e.preventDefault();

        tooltipEl.style.transition = '';

        const overlayEl = tooltipEl.parentElement;
        const overlayRect = overlayEl?.getBoundingClientRect();
        const tipRect = tooltipEl.getBoundingClientRect();
        const currentLeft = overlayRect ? tipRect.left - overlayRect.left : parseFloat(tooltipEl.style.left) || 0;
        const currentTop = overlayRect ? tipRect.top - overlayRect.top : parseFloat(tooltipEl.style.top) || 0;

        dragStateRef.current = {
          dragging: true,
          startMouseX: e.clientX,
          startMouseY: e.clientY,
          startLeft: currentLeft,
          startTop: currentTop,
        };
      };

      const onMouseMove = (e: MouseEvent) => {
        const ds = dragStateRef.current;
        if (!ds?.dragging) return;

        const dx = e.clientX - ds.startMouseX;
        const dy = e.clientY - ds.startMouseY;

        const newPos = clampTooltipPosition(
          { left: ds.startLeft + dx, top: ds.startTop + dy },
          tooltipEl.offsetWidth,
          tooltipEl.offsetHeight,
        );

        tooltipPosRef.current = newPos;
        applyTooltipPosition(tooltipEl, newPos);
      };

      const onMouseUp = () => {
        dragStateRef.current = null;
      };

      tooltipEl.addEventListener('mousedown', onMouseDown);
      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);

      return () => {
        tooltipEl.removeEventListener('mousedown', onMouseDown);
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);
      };
    },
    [clampTooltipPosition, applyTooltipPosition],
  );

  useEffect(() => {
    const tooltipEl = indexTooltipRef.current;
    if (!tooltipEl || !chart) return;
    return setupDrag(tooltipEl);
  }, [chart, setupDrag]);

  // ---------------------------------------------------------------------------
  // Hot path: runs on every replay tick
  // ---------------------------------------------------------------------------
  const updateIndexDom = useCallback(
    (index: number) => {
      const lineEl = indexLineRef.current;
      const tooltipEl = indexTooltipRef.current;
      const dotEls = indexDotsRef.current;

      if (!chart || !lineEl || !tooltipEl || !isInitializedRef.current) return;

      const xData = xDataRef.current;
      const yData = yDataRef.current;
      const xAxis = xAxisRef.current;
      const yAxis = yAxisRef.current;
      const seriesNames = seriesNamesRef.current;

      const xValue = xData[index];
      const yValues = yData[index] || [];

      if (xValue == null) return;

      const rect = gridRectRef.current;
      if (!rect) {
        currentIndexRef.current = index;
        return;
      }

      // Position index line
      const px = chart.convertToPixel({ xAxisIndex: 0 }, xValue) as number;
      lineEl.style.transform = `translate3d(${px}px, ${rect.y}px, 0)`;
      lineEl.style.height = `${rect.height}px`;
      lineEl.style.display = 'block';

      // Position dots
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

      tooltipEl.innerHTML = `
        <div style="display:flex;justify-content:center;gap:4px;margin-bottom:6px;">
          <span style="display:inline-block;width:5px;height:5px;border-radius:50%;background:rgba(160,160,160,0.7);"></span>
          <span style="display:inline-block;width:5px;height:5px;border-radius:50%;background:rgba(160,160,160,0.7);"></span>
          <span style="display:inline-block;width:5px;height:5px;border-radius:50%;background:rgba(160,160,160,0.7);"></span>
        </div>
        <div>${xLabel}</div>
        ${yLines.join('')}
      `;

      // Place tooltip at default position on first show, then leave it wherever
      // the user dropped it. Clamping after content changes is handled by ResizeObserver.
      if (!tooltipPosRef.current) {
        const defaultPos = defaultTooltipPosition();
        if (defaultPos) {
          tooltipPosRef.current = defaultPos;
          applyTooltipPosition(tooltipEl, defaultPos);
        }
      }

      tooltipEl.style.display = 'block';
    },
    [chart, defaultTooltipPosition, applyTooltipPosition],
  );

  // ---------------------------------------------------------------------------
  // Grid rect update — triggered on chart finish (includes resize and data-zoom)
  // ---------------------------------------------------------------------------
  const updateGridRect = useCallback(() => {
    if (!chart) return;

    const rect = computeGridRect(chart);
    if (rect) {
      gridRectRef.current = rect;

      // After grid changes, clamp the tooltip back into the (possibly shifted) bounds
      const tooltipEl = indexTooltipRef.current;
      const pos = tooltipPosRef.current;
      if (tooltipEl && pos) {
        const clamped = clampTooltipPosition(pos, tooltipEl.offsetWidth, tooltipEl.offsetHeight);
        if (clamped.left !== pos.left || clamped.top !== pos.top) {
          tooltipPosRef.current = clamped;
          if (tooltipEl.style.display !== 'none') {
            applyTooltipPosition(tooltipEl, clamped);
          }
        }
      }

      if (currentIndexRef.current !== undefined && isInitializedRef.current) {
        updateIndexDom(currentIndexRef.current);
      }
    }
  }, [chart, computeGridRect, clampTooltipPosition, applyTooltipPosition, updateIndexDom]);

  // Initialize when chart becomes available
  useEffect(() => {
    if (!chart) return;

    chart.on('finished', updateGridRect);
    chart.on('dataZoom', updateGridRect);
    chart.on('restore', updateGridRect);

    requestAnimationFrame(() => {
      isInitializedRef.current = true;
      chart.resize();
    });

    return () => {
      chart.off('finished', updateGridRect);
    };
  }, [chart, updateGridRect]);

  // Subscribe to replay controller
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
      <div
        ref={indexTooltipRef}
        className={`${styles.indexTooltip} ${styles.indexTooltipDraggable}`}
      />
    </div>
  );
}