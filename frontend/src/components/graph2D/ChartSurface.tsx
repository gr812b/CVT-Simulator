import { useLayoutEffect, useRef, type CSSProperties } from 'react';
import { init, type ECharts, type EChartsOption } from 'echarts';

/** One synchronous ECharts lifetime per DOM surface, including StrictMode replay. */
export function ChartSurface({ option, style, onReady, onEvents }: {
  option: EChartsOption; style: CSSProperties;
  onReady: (chart: ECharts | null) => void;
  onEvents: Record<string, () => void>;
}) {
  const element = useRef<HTMLDivElement>(null);
  const chart = useRef<ECharts | null>(null);
  const latest = useRef({ option, onEvents });
  latest.current = { option, onEvents };
  const applied = useRef<EChartsOption | null>(null);
  useLayoutEffect(() => {
    if (!element.current) return;
    const current = init(element.current);
    chart.current = current;
    // Publish the live instance only after its axes and data exist. No hover or
    // asynchronous wrapper "ready" callback is needed for the first paint.
    current.setOption(latest.current.option, { notMerge: true, lazyUpdate: false });
    applied.current = latest.current.option;
    const events = ['datazoom', 'legendselectchanged', 'restore'];
    const handlers = events.map(name => () => latest.current.onEvents[name]?.());
    events.forEach((name, i) => current.on(name, handlers[i]));
    const resize = new ResizeObserver(() => {
      if (!current.isDisposed()) current.resize({ animation: { duration: 0 } });
    });
    resize.observe(element.current);
    onReady(current);
    return () => {
      resize.disconnect();
      events.forEach((name, i) => current.off(name, handlers[i]));
      if (chart.current === current) {
        chart.current = null; applied.current = null; onReady(null);
      }
      current.dispose();
    };
  }, [onReady]);
  useLayoutEffect(() => {
    const current = chart.current;
    if (!current || current.isDisposed() || applied.current === option) return;
    current.setOption(option, { notMerge: false, lazyUpdate: false, replaceMerge: ['series'] });
    applied.current = option;
  }, [option]);
  return <div ref={element} data-chart-surface style={{ ...style, position: 'relative' }}/>;
}
