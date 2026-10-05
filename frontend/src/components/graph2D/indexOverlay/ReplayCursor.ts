import { graphic, type ECharts } from 'echarts';
import { CHART_COLORS } from '../chartOptions';

export interface CursorData {
  xData: number[];
  yData: Array<Array<number | null>>;
  seriesNames: string[];
}
/** A persistent renderer layer, independent of ECharts' hover axisPointer. */
export class ReplayCursor {
  private readonly group = new graphic.Group({ silent: true });
  private readonly line = new graphic.Line({
    silent: true,
    zlevel: 10,
    z: 100,
    style: { lineWidth: 1, lineDash: [4, 4] },
  });
  private readonly dots: InstanceType<typeof graphic.Circle>[] = [];
  private signature = '';
  private index = 0;
  constructor(
    private readonly chart: ECharts,
    private data: CursorData,
  ) {
    this.group.add(this.line);
    chart.getZr().add(this.group);
    chart.on('rendered', this.draw);
    chart.on('datazoom', this.draw);
    chart.on('legendselectchanged', this.draw);
    this.draw();
  }
  refresh() {
    this.draw();
  }
  update(data: CursorData) {
    this.data = data;
    this.signature = '';
    this.draw();
  }
  seek(index: number) {
    this.index = index;
    this.draw();
  }
  private draw = () => {
    const chart = this.chart;
    if (chart.isDisposed()) return;
    // The resolved grid rectangle accounts for labels, zoom and compact layouts.
    // @ts-expect-error getModel is a runtime ECharts API omitted from its public type.
    const model = chart.getModel();
    const rect = model.getComponent('grid')?.coordinateSystem?.getRect();
    if (!rect) return;
    const { xData, yData, seriesNames } = this.data;
    const x = chart.convertToPixel(
      { xAxisIndex: 0 },
      xData[this.index],
    ) as number;
    const visible =
      Number.isFinite(x) && x >= rect.x - 0.5 && x <= rect.x + rect.width + 0.5;
    const option = chart.getOption() as {
      legend?: { selected?: Record<string, boolean> }[];
    };
    const selected = option.legend?.[0]?.selected ?? {};
    const ys = (yData[this.index] ?? []).map((value, i) =>
      value == null || selected[seriesNames[i]] === false
        ? NaN
        : (chart.convertToPixel({ yAxisIndex: 0 }, value) as number),
    );
    const colors = CHART_COLORS.LINES;
    const signature = JSON.stringify([
      x,
      ys,
      visible,
      rect.x,
      rect.y,
      rect.width,
      rect.height,
      colors,
      CHART_COLORS.TEXT,
    ]);
    // Drawing emits rendered again. Only changed geometry schedules another paint.
    if (signature === this.signature) return;
    this.signature = signature;
    this.line.attr({
      ignore: !visible,
      shape: { x1: x, y1: rect.y, x2: x, y2: rect.y + rect.height },
      style: { stroke: CHART_COLORS.TEXT },
    });
    while (this.dots.length < ys.length) {
      const dot = new graphic.Circle({
        silent: true,
        zlevel: 10,
        z: 101,
        shape: { r: 3.5 },
      });
      this.dots.push(dot);
      this.group.add(dot);
    }
    this.dots.forEach((dot, i) =>
      dot.attr({
        ignore:
          !visible ||
          !Number.isFinite(ys[i]) ||
          ys[i] < rect.y ||
          ys[i] > rect.y + rect.height,
        shape: { cx: x, cy: ys[i] },
        style: {
          fill: colors[i % colors.length],
          stroke: CHART_COLORS.BACKGROUND,
          lineWidth: 1,
        },
      }),
    );
    chart.getZr().refresh();
  };
  dispose() {
    if (this.chart.isDisposed()) return;
    this.chart.off('rendered', this.draw);
    this.chart.off('datazoom', this.draw);
    this.chart.off('legendselectchanged', this.draw);
    this.chart.getZr().remove(this.group);
  }
}
