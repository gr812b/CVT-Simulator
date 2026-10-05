import { useRef, useEffect, useCallback } from 'react';
import type { ECharts } from 'echarts';
import { ReplayEventType } from '@utils/reportReplay';
import styles from './IndexOverlay.module.scss';

interface IndexOverlayProps {
  xData: number[];
  yData: Array<Array<number | null>>;
  seriesNames?: string[];
  replayController: {
    on: (
      handler: (event: { type: string; currentIndex?: number }) => void,
    ) => () => void;
  };
  chart: ECharts | null;
}

/** Lightweight replay cursor. Values remain available through the hover tooltip. */
export function IndexOverlay({
  xData,
  yData,
  seriesNames = [],
  replayController,
  chart,
}: IndexOverlayProps) {
  const line = useRef<HTMLDivElement>(null);
  const dots = useRef<(HTMLDivElement | null)[]>([]);
  const index = useRef(0);
  const data = useRef({ xData, yData, seriesNames });
  data.current = { xData, yData, seriesNames };
  const grid = useRef<{
    x: number;
    y: number;
    width: number;
    height: number;
  } | null>(null);
  const selected = useRef<Record<string, boolean>>({});

  const draw = useCallback(() => {
    if (!chart || chart.isDisposed() || !line.current || !grid.current) return;
    const rect = grid.current;
    const { xData, yData, seriesNames } = data.current;
    const x = chart.convertToPixel(
      { xAxisIndex: 0 },
      xData[index.current],
    ) as number;
    const visible =
      Number.isFinite(x) && x >= rect.x - 0.5 && x <= rect.x + rect.width + 0.5;
    line.current.style.display = visible ? 'block' : 'none';
    line.current.style.transform = `translate3d(${x}px, ${rect.y}px, 0)`;
    line.current.style.height = `${rect.height}px`;
    dots.current.forEach((dot, i) => {
      if (!dot) return;
      const value = yData[index.current]?.[i];
      const y =
        value == null
          ? NaN
          : (chart.convertToPixel({ yAxisIndex: 0 }, value) as number);
      dot.style.display =
        visible &&
        Number.isFinite(y) &&
        y >= rect.y &&
        y <= rect.y + rect.height &&
        selected.current[seriesNames[i]] !== false
          ? 'block'
          : 'none';
      dot.style.transform = `translate3d(${x - 4}px, ${y - 4}px, 0)`;
    });
  }, [chart]);

  useEffect(() => {
    if (!chart || chart.isDisposed()) return;
    const refresh = () => {
      if (chart.isDisposed()) return;
      // ECharts exposes axis conversion but not its resolved grid rectangle.
      // @ts-expect-error ECharts getModel exists at runtime, absent from its type export.
      const model = chart.getModel();
      const xAxis = model.getComponent('xAxis')?.axis;
      const yAxis = model.getComponent('yAxis')?.axis;
      if (!xAxis || !yAxis) return;
      const xs = xAxis.scale
        .getExtent()
        .map(
          (value: number) =>
            chart.convertToPixel({ xAxisIndex: 0 }, value) as number,
        );
      const ys = yAxis.scale
        .getExtent()
        .map(
          (value: number) =>
            chart.convertToPixel({ yAxisIndex: 0 }, value) as number,
        );
      if (![...xs, ...ys].every(Number.isFinite)) return;
      grid.current = {
        x: Math.min(...xs),
        y: Math.min(...ys),
        width: Math.abs(xs[1] - xs[0]),
        height: Math.abs(ys[1] - ys[0]),
      };
      const option = chart.getOption() as {
        legend?: { selected?: Record<string, boolean> }[];
      };
      selected.current = option.legend?.[0]?.selected ?? {};
      draw();
    };
    // Initial lazy setOption may render after onChartReady; do not depend on
    // tooltip hover or an animation finishing to establish the cursor bounds.
    const events = ['rendered', 'finished', 'datazoom', 'legendselectchanged'];
    events.forEach((event) => chart.on(event, refresh));
    const resize = new ResizeObserver(refresh);
    resize.observe(chart.getDom());
    const frame = requestAnimationFrame(refresh);
    refresh();
    return () => {
      cancelAnimationFrame(frame);
      resize.disconnect();
      events.forEach((event) => chart.off(event, refresh));
      grid.current = null;
    };
  }, [chart, draw]);

  useEffect(() => {
    draw();
  }, [draw, xData, yData, seriesNames]);

  useEffect(
    () =>
      replayController.on((event) => {
        if (
          event.type === ReplayEventType.Progress &&
          event.currentIndex !== undefined
        ) {
          index.current = event.currentIndex;
          draw();
        }
      }),
    [replayController, draw],
  );

  return (
    <div className={styles.indexOverlay} aria-hidden="true">
      <div ref={line} className={styles.indexLine} />
      {yData[0]?.map((_, i) => (
        <div
          key={i}
          ref={(el) => {
            dots.current[i] = el;
          }}
          className={styles.indexDot}
          style={{ background: `var(--line${i + 1}, white)` }}
        />
      ))}
    </div>
  );
}
