import type { ECharts } from 'echarts';
import { CHART_COLORS } from '../chartOptions';

export interface CursorData {
  xData: number[];
  yData: Array<Array<number | null>>;
  seriesNames: string[];
}
const NS = 'http://www.w3.org/2000/svg';
type GridRect = { x: number; y: number; width: number; height: number };
type ModelAccess = { getModel(): { getComponent(name: string): { coordinateSystem?: { getRect(): GridRect } } | undefined } };

/** DOM overlay: ECharts option updates cannot erase it from ZRender's scene. */
export class ReplayCursor {
  private readonly overlay = document.createElementNS(NS, 'svg');
  private readonly line = document.createElementNS(NS, 'line');
  private readonly dots: SVGCircleElement[] = [];
  private index = 0;
  private disposed = false;
  constructor(private readonly chart: ECharts, private data: CursorData) {
    this.overlay.setAttribute('aria-hidden', 'true');
    this.overlay.setAttribute('data-playback-cursor', '');
    Object.assign(this.overlay.style, {
      position: 'absolute', inset: '0', width: '100%', height: '100%',
      pointerEvents: 'none', overflow: 'hidden', zIndex: '2', visibility: 'hidden',
    });
    this.line.setAttribute('stroke-width', '1.25');
    this.line.setAttribute('stroke-dasharray', '4 4');
    this.line.setAttribute('data-cursor-line', '');
    this.overlay.append(this.line);
    chart.getDom().append(this.overlay);
    chart.on('rendered', this.draw);
    chart.on('datazoom', this.draw);
    chart.on('legendselectchanged', this.draw);
    this.draw();
  }
  refresh() { this.draw(); }
  update(data: CursorData) { this.data = data; this.draw(); }
  seek(index: number) {
    if (!Number.isFinite(index)) return;
    this.index = Math.max(0, Math.trunc(index)); this.draw();
  }
  private draw = () => {
    if (this.disposed || this.chart.isDisposed()) return;
    const chart = this.chart;
    const rect = (chart as unknown as ModelAccess).getModel().getComponent('grid')?.coordinateSystem?.getRect();
    this.overlay.dataset.index = String(this.index);
    const { xData, yData, seriesNames } = this.data;
    if (!rect || this.index >= xData.length) { this.overlay.style.visibility = 'hidden'; return; }
    const x = chart.convertToPixel({ xAxisIndex: 0 }, xData[this.index]) as number;
    const visible = Number.isFinite(x) && x >= rect.x - 0.5 && x <= rect.x + rect.width + 0.5;
    this.overlay.style.visibility = visible ? 'visible' : 'hidden';
    if (!visible) return;
    this.line.setAttribute('x1', String(x)); this.line.setAttribute('x2', String(x));
    this.line.setAttribute('y1', String(rect.y)); this.line.setAttribute('y2', String(rect.y + rect.height));
    this.line.setAttribute('stroke', CHART_COLORS.TEXT);
    const option = chart.getOption() as { legend?: { selected?: Record<string, boolean> }[] };
    const selected = option.legend?.[0]?.selected ?? {};
    const ys = yData[this.index] ?? [];
    while (this.dots.length < ys.length) {
      const dot = document.createElementNS(NS, 'circle');
      dot.setAttribute('r', '3.5'); dot.setAttribute('stroke-width', '1');
      this.dots.push(dot); this.overlay.append(dot);
    }
    const colors = CHART_COLORS.LINES;
    this.dots.forEach((dot, i) => {
      const value = ys[i];
      const y = value == null ? NaN : chart.convertToPixel({ yAxisIndex: 0 }, value) as number;
      const show = Number.isFinite(y) && y >= rect.y && y <= rect.y + rect.height && selected[seriesNames[i]] !== false;
      dot.style.visibility = show ? 'inherit' : 'hidden';
      if (!show) return;
      dot.setAttribute('cx', String(x)); dot.setAttribute('cy', String(y));
      dot.setAttribute('fill', colors[i % colors.length]);
      dot.setAttribute('stroke', CHART_COLORS.BACKGROUND);
    });
  };
  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    if (!this.chart.isDisposed()) {
      this.chart.off('rendered', this.draw);
      this.chart.off('datazoom', this.draw);
      this.chart.off('legendselectchanged', this.draw);
    }
    // Always remove DOM, even when the parent chart was already disposed.
    this.overlay.remove();
  }
}
