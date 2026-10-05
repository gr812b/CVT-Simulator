import { useRef, useEffect } from 'react';
import type { ECharts } from 'echarts';
import { ReplayEventType } from '@utils/reportReplay';
import { ReplayCursor } from './ReplayCursor';
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
export function IndexOverlay({
  xData,
  yData,
  seriesNames = [],
  replayController,
  chart,
}: IndexOverlayProps) {
  const cursor = useRef<ReplayCursor | null>(null);
  const data = useRef({ xData, yData, seriesNames });
  data.current = { xData, yData, seriesNames };
  useEffect(() => {
    if (!chart || chart.isDisposed()) return;
    const next = new ReplayCursor(chart, data.current);
    cursor.current = next;
    let frame = requestAnimationFrame(() => next.refresh());
    const resize = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => next.refresh());
    });
    resize.observe(chart.getDom());
    const unsubscribe = replayController.on((event) => {
      if (
        event.type === ReplayEventType.Progress &&
        event.currentIndex !== undefined
      )
        next.seek(event.currentIndex);
    });
    return () => {
      unsubscribe();
      cancelAnimationFrame(frame);
      resize.disconnect();
      next.dispose();
      cursor.current = null;
    };
  }, [chart, replayController]);
  useEffect(() => {
    cursor.current?.update(data.current);
  }, [xData, yData, seriesNames]);
  return null;
}
