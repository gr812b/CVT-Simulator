import { useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import type { ValidationRunRecord } from '@api/client';
import { parseDynoCsv } from '@pages/validation/data';
import {
  buildDynoAnalysis,
  DYNO_ANALYSIS_WINDOWS_MS,
  RECOMMENDED_DYNO_WINDOW_MS,
  SECONDARY_INERTIA_HIGH_KG_M2,
  SECONDARY_INERTIA_LOW_KG_M2,
  type DynoAnalysisResult,
  type DynoAnalysisWindowMs,
  type DynoTracePoint,
  type EfficiencyRatioPoint,
} from '@pages/validation/rawDynoAnalysis';
import styles from './DynoAnalysisSection.module.scss';

interface Props {
  run: ValidationRunRecord;
}

const WINDOW_COLORS: Record<DynoAnalysisWindowMs, string> = {
  5: '#60a5fa',
  10: '#f59e0b',
  20: '#34d399',
  50: '#f472b6',
  100: '#a78bfa',
  250: '#ef4444',
};

function cssColor(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function formatNumber(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 1000) return value.toFixed(0);
  if (magnitude >= 100) return value.toFixed(1);
  if (magnitude >= 10) return value.toFixed(2);
  return value.toFixed(3);
}

function finiteBounds(point: DynoTracePoint): [number, number] | null {
  if (
    typeof point.lower === 'number' && Number.isFinite(point.lower)
    && typeof point.upper === 'number' && Number.isFinite(point.upper)
  ) return [point.lower, point.upper];
  if (typeof point.uncertainty === 'number' && Number.isFinite(point.uncertainty)) {
    return [point.value - point.uncertainty, point.value + point.uncertainty];
  }
  return null;
}

function traceSeries(
  selected: DynoAnalysisWindowMs[],
  traces: Record<DynoAnalysisWindowMs, DynoTracePoint[]>,
): Record<string, unknown>[] {
  return selected.map((windowMs) => {
    const color = WINDOW_COLORS[windowMs];
    return {
      name: `${windowMs} ms`,
      type: 'line',
      symbol: 'none',
      showSymbol: false,
      connectNulls: false,
      lineStyle: { color, width: windowMs === RECOMMENDED_DYNO_WINDOW_MS ? 2.6 : 1.6, opacity: 0.92 },
      itemStyle: { color },
      emphasis: { focus: 'series' },
      data: traces[windowMs].map((point) => ({
        value: [point.timeS, point.value],
        lower: finiteBounds(point)?.[0] ?? null,
        upper: finiteBounds(point)?.[1] ?? null,
      })),
    };
  });
}

function traceTimeDomain(traces: Record<DynoAnalysisWindowMs, DynoTracePoint[]>): [number, number] | null {
  let minimum = Number.POSITIVE_INFINITY;
  let maximum = Number.NEGATIVE_INFINITY;
  for (const windowMs of DYNO_ANALYSIS_WINDOWS_MS) {
    for (const point of traces[windowMs]) {
      if (!Number.isFinite(point.timeS)) continue;
      minimum = Math.min(minimum, point.timeS);
      maximum = Math.max(maximum, point.timeS);
    }
  }
  return Number.isFinite(minimum) && Number.isFinite(maximum) && maximum > minimum
    ? [minimum, maximum]
    : null;
}

function AnalysisTimeChart({
  title,
  subtitle,
  unit,
  selected,
  traces,
  yMin,
  yMax,
}: {
  title: string;
  subtitle?: string;
  unit: string;
  selected: DynoAnalysisWindowMs[];
  traces: Record<DynoAnalysisWindowMs, DynoTracePoint[]>;
  yMin?: number;
  yMax?: number;
}) {
  const [zoomRange, setZoomRange] = useState<{ start: number; end: number } | null>(null);
  const timeDomain = useMemo(() => traceTimeDomain(traces), [traces]);
  const onEvents = useMemo(() => ({
    datazoom: (event: unknown) => {
      if (typeof event !== 'object' || event === null) return;
      const record = event as { start?: unknown; end?: unknown; batch?: Array<{ start?: unknown; end?: unknown }> };
      const source = Array.isArray(record.batch) && record.batch.length > 0 ? record.batch[0] : record;
      if (typeof source.start === 'number' && Number.isFinite(source.start) && typeof source.end === 'number' && Number.isFinite(source.end)) {
        setZoomRange({ start: source.start, end: source.end });
      }
    },
    restore: () => setZoomRange(null),
  }), []);
  const option = useMemo<EChartsOption>(() => {
    const text = cssColor('--text-color', '#f4f4f5');
    const grid = cssColor('--grid-color', '#404040');
    const tooltipBackground = cssColor('--tooltip-bg', '#202124');
    return {
      animation: false,
      backgroundColor: 'transparent',
      textStyle: { color: text },
      tooltip: {
        trigger: 'axis',
        backgroundColor: tooltipBackground,
        borderColor: grid,
        textStyle: { color: text },
        axisPointer: { type: 'line', snap: false, lineStyle: { color: grid } },
        formatter: (params: unknown): string => {
          const entries = Array.isArray(params) ? params : [params];
          const lines: string[] = [];
          let time: number | null = null;
          for (const entry of entries) {
            if (typeof entry !== 'object' || entry === null) continue;
            const record = entry as { seriesName?: string; data?: unknown };
            const data = record.data;
            let value: unknown = data;
            let lower: number | null = null;
            let upper: number | null = null;
            if (typeof data === 'object' && data !== null && !Array.isArray(data)) {
              const point = data as { value?: unknown; lower?: unknown; upper?: unknown };
              value = point.value;
              lower = typeof point.lower === 'number' && Number.isFinite(point.lower) ? point.lower : null;
              upper = typeof point.upper === 'number' && Number.isFinite(point.upper) ? point.upper : null;
            }
            if (!Array.isArray(value) || typeof value[0] !== 'number' || typeof value[1] !== 'number') continue;
            time ??= value[0];
            const suffix = lower !== null && upper !== null && record.seriesName === `${RECOMMENDED_DYNO_WINDOW_MS} ms`
              ? ` · uncertainty ${formatNumber(lower)}–${formatNumber(upper)} ${unit}`
              : '';
            lines.push(`${record.seriesName ?? 'Trace'}: ${formatNumber(value[1])} ${unit}${suffix}`);
          }
          if (time === null) return lines.join('<br/>');
          return [`<strong>${time.toFixed(3)} s</strong>`, ...lines].join('<br/>');
        },
      },
      toolbox: {
        show: true,
        right: 4,
        top: 0,
        feature: {
          dataZoom: { yAxisIndex: 'none', title: { zoom: 'Zoom', back: 'Zoom back' } },
          restore: { title: 'Reset zoom' },
        },
        iconStyle: { borderColor: text },
      },
      dataZoom: [{
        type: 'inside',
        xAxisIndex: 0,
        filterMode: 'none',
        start: zoomRange?.start ?? 0,
        end: zoomRange?.end ?? 100,
        zoomOnMouseWheel: false,
        moveOnMouseWheel: false,
        moveOnMouseMove: false,
      }],
      grid: { left: 74, right: 32, top: 42, bottom: 62, containLabel: true },
      xAxis: {
        type: 'value',
        scale: true,
        min: timeDomain?.[0],
        max: timeDomain?.[1],
        name: 'Time from run start [s]',
        nameLocation: 'middle',
        nameGap: 36,
        nameTextStyle: { color: text },
        axisLabel: { color: text },
        axisLine: { lineStyle: { color: grid } },
        axisTick: { lineStyle: { color: grid } },
        splitLine: { lineStyle: { color: grid, opacity: 0.6 } },
      },
      yAxis: {
        type: 'value',
        min: yMin,
        max: yMax,
        name: unit,
        nameLocation: 'middle',
        nameGap: 52,
        nameTextStyle: { color: text },
        axisLabel: { color: text },
        axisLine: { lineStyle: { color: grid } },
        axisTick: { lineStyle: { color: grid } },
        splitLine: { lineStyle: { color: grid, opacity: 0.6 } },
      },
      series: traceSeries(selected, traces),
    };
  }, [selected, timeDomain, traces, unit, yMax, yMin, zoomRange]);

  return (
    <article className={styles.chartCard}>
      <div className={styles.chartHeading}>
        <div>
          <h3>{title}</h3>
          {subtitle !== undefined && <p>{subtitle}</p>}
        </div>
      </div>
      <ReactECharts
        option={option}
        className={styles.chart}
        notMerge={false}
        replaceMerge={['series']}
        lazyUpdate
        onEvents={onEvents}
      />
    </article>
  );
}

function RecommendedTimeChart({
  title,
  subtitle,
  unit,
  trace,
  yMin,
  yMax,
}: {
  title: string;
  subtitle?: string;
  unit: string;
  trace: DynoTracePoint[];
  yMin?: number;
  yMax?: number;
}) {
  const traces = useMemo(() => {
    const empty = {} as Record<DynoAnalysisWindowMs, DynoTracePoint[]>;
    for (const windowMs of DYNO_ANALYSIS_WINDOWS_MS) empty[windowMs] = [];
    empty[RECOMMENDED_DYNO_WINDOW_MS] = trace;
    return empty;
  }, [trace]);
  return (
    <AnalysisTimeChart
      title={title}
      subtitle={subtitle}
      unit={unit}
      selected={[RECOMMENDED_DYNO_WINDOW_MS]}
      traces={traces}
      yMin={yMin}
      yMax={yMax}
    />
  );
}

function EfficiencyRatioChart({ points }: { points: EfficiencyRatioPoint[] }) {
  const option = useMemo<EChartsOption>(() => {
    const text = cssColor('--text-color', '#f4f4f5');
    const grid = cssColor('--grid-color', '#404040');
    const primary = cssColor('--primary', '#bb0808');
    const tooltipBackground = cssColor('--tooltip-bg', '#202124');
    const pointColor = '#a78bfa';
    const filtered = points.filter((point) => (
      point.ratio >= 1 && point.ratio <= 6
      && point.efficiencyPct >= 0 && point.efficiencyPct <= 100
    ));
    return {
      animation: false,
      backgroundColor: 'transparent',
      textStyle: { color: text },
      tooltip: {
        trigger: 'item',
        backgroundColor: tooltipBackground,
        borderColor: grid,
        textStyle: { color: text },
        formatter: (params: unknown) => {
          if (typeof params !== 'object' || params === null) return '';
          const data = (params as { data?: unknown }).data;
          if (typeof data !== 'object' || data === null || Array.isArray(data)) return '';
          const point = data as { value?: unknown; lower?: unknown; upper?: unknown };
          if (!Array.isArray(point.value) || typeof point.value[0] !== 'number' || typeof point.value[1] !== 'number') return '';
          const lower = typeof point.lower === 'number' && Number.isFinite(point.lower) ? point.lower : null;
          const upper = typeof point.upper === 'number' && Number.isFinite(point.upper) ? point.upper : null;
          const range = lower !== null && upper !== null ? `<br/>Uncertainty: ${lower.toFixed(1)}–${upper.toFixed(1)}%` : '';
          return `<strong>Ratio ${point.value[0].toFixed(3)}</strong><br/>Efficiency: ${point.value[1].toFixed(1)}%${range}`;
        },
      },
      toolbox: {
        show: true,
        right: 4,
        top: 0,
        feature: { dataZoom: {}, restore: { title: 'Reset zoom' } },
        iconStyle: { borderColor: text },
        emphasis: { iconStyle: { borderColor: primary } },
      },
      grid: { left: 74, right: 32, top: 42, bottom: 62, containLabel: true },
      xAxis: {
        type: 'value',
        scale: true,
        min: 1,
        max: 6,
        name: 'Speed ratio  ωp / ωs',
        nameLocation: 'middle',
        nameGap: 36,
        nameTextStyle: { color: text },
        axisLabel: { color: text },
        axisLine: { lineStyle: { color: grid } },
        splitLine: { lineStyle: { color: grid, opacity: 0.6 } },
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 100,
        name: 'Efficiency [%]',
        nameLocation: 'middle',
        nameGap: 52,
        nameTextStyle: { color: text },
        axisLabel: { color: text },
        axisLine: { lineStyle: { color: grid } },
        splitLine: { lineStyle: { color: grid, opacity: 0.6 } },
      },
      series: [
        {
          name: '100 ms samples',
          type: 'scatter',
          symbolSize: 6,
          itemStyle: { color: pointColor, opacity: 0.58 },
          data: filtered.map((point) => ({
            value: [point.ratio, point.efficiencyPct],
            lower: point.lowerPct,
            upper: point.upperPct,
          })),
        },
      ],
    };
  }, [points]);

  return (
    <article className={styles.chartCard}>
      <div className={styles.chartHeading}>
        <div>
          <h3>Efficiency vs speed ratio</h3>
          <p>100 ms samples only. No fitted or binned trend line is imposed; hover a point to see its timing + inertia uncertainty range.</p>
        </div>
      </div>
      <ReactECharts option={option} className={styles.chart} notMerge={false} lazyUpdate />
    </article>
  );
}

function healthText(analysis: DynoAnalysisResult): string {
  if (analysis.health === undefined) return 'Legacy wide RPM source';
  const device = analysis.health.primaryDeviceMissingEdges + analysis.health.secondaryDeviceMissingEdges;
  const downstream = analysis.health.primaryDownstreamMissingPackets + analysis.health.secondaryDownstreamMissingPackets;
  if (device === 0 && downstream === 0) return '0 detected RPM losses';
  return `${device} device-edge · ${downstream} downstream losses`;
}

export function DynoAnalysisSection({ run }: Props) {
  const [selectedWindows, setSelectedWindows] = useState<DynoAnalysisWindowMs[]>([RECOMMENDED_DYNO_WINDOW_MS]);
  const prepared = useMemo(() => {
    try {
      const parsedData = parseDynoCsv(run.sourceFilename, run.rawCsv);
      return {
        analysis: buildDynoAnalysis({
          rawCsv: run.rawCsv,
          parsedData,
          cropStartS: run.cropStartS,
          cropEndS: run.cropEndS,
          workspaceSnapshot: run.workspaceSnapshot,
          resolvedDocument: run.resolvedDocument,
        }),
        error: null as string | null,
      };
    } catch (cause) {
      return {
        analysis: null,
        error: cause instanceof Error ? cause.message : String(cause),
      };
    }
  }, [run.cropEndS, run.cropStartS, run.rawCsv, run.resolvedDocument, run.sourceFilename, run.workspaceSnapshot]);

  const analysis = prepared.analysis;
  const primaryRpm = useMemo(() => analysis === null
    ? null
    : Object.fromEntries(DYNO_ANALYSIS_WINDOWS_MS.map((windowMs) => [windowMs, analysis.windows[windowMs].primaryRpm])) as Record<DynoAnalysisWindowMs, DynoTracePoint[]>, [analysis]);
  const secondaryRpm = useMemo(() => analysis === null
    ? null
    : Object.fromEntries(DYNO_ANALYSIS_WINDOWS_MS.map((windowMs) => [windowMs, analysis.windows[windowMs].secondaryRpm])) as Record<DynoAnalysisWindowMs, DynoTracePoint[]>, [analysis]);
  const primaryPower = useMemo(() => analysis === null
    ? null
    : Object.fromEntries(DYNO_ANALYSIS_WINDOWS_MS.map((windowMs) => [windowMs, analysis.windows[windowMs].primaryPowerKw])) as Record<DynoAnalysisWindowMs, DynoTracePoint[]>, [analysis]);
  const secondaryPower = useMemo(() => analysis === null
    ? null
    : Object.fromEntries(DYNO_ANALYSIS_WINDOWS_MS.map((windowMs) => [windowMs, analysis.windows[windowMs].secondaryPowerKw])) as Record<DynoAnalysisWindowMs, DynoTracePoint[]>, [analysis]);
  const ratio = useMemo(() => analysis === null
    ? null
    : Object.fromEntries(DYNO_ANALYSIS_WINDOWS_MS.map((windowMs) => [windowMs, analysis.windows[windowMs].ratio])) as Record<DynoAnalysisWindowMs, DynoTracePoint[]>, [analysis]);

  if (analysis === null || primaryRpm === null || secondaryRpm === null || primaryPower === null || secondaryPower === null || ratio === null) {
    return (
      <section className={styles.section}>
        <p className={styles.warning}>Experimental dyno analysis is unavailable for this saved run: {prepared.error ?? 'the required RPM evidence is missing.'}</p>
      </section>
    );
  }

  const recommended = analysis.windows[RECOMMENDED_DYNO_WINDOW_MS];

  const toggleWindow = (windowMs: DynoAnalysisWindowMs) => {
    setSelectedWindows((current) => {
      if (current.includes(windowMs)) {
        if (current.length === 1) return current;
        return current.filter((value) => value !== windowMs);
      }
      return [...current, windowMs].sort((a, b) => a - b);
    });
  };

  return (
    <section className={styles.section}>
      <div className={styles.intro}>
        <div>
          <span className={styles.eyebrow}>Experimental dyno analysis</span>
          <h2>Measured drivetrain behaviour</h2>
          <p>
            This view is derived only from the saved experimental evidence. RPM is reconstructed over one full revolution to suppress tooth-pitch bias; secondary inertial power uses the kinetic-energy rate instead of differentiating noisy instantaneous RPM.
          </p>
        </div>
        <div className={styles.metaGrid}>
          <span>{analysis.sourceLabel}</span>
          <span>{healthText(analysis)}</span>
          <span>CH440 · {analysis.engineCurveSource}</span>
          <span>Jₛ {SECONDARY_INERTIA_LOW_KG_M2.toFixed(4)}–{SECONDARY_INERTIA_HIGH_KG_M2.toFixed(4)} kg·m²</span>
        </div>
      </div>

      {analysis.warnings.map((warning) => <p key={warning} className={styles.warning}>{warning}</p>)}

      <div className={styles.windowPanel}>
        <div>
          <strong>Sampling window</strong>
          <p>Turn windows on together for comparison or isolate one. 100 ms is recommended for efficiency because it spans multiple CH440 four-stroke cycles without the heavy transient smearing of 250 ms.</p>
        </div>
        <div className={styles.windowActions}>
          <div className={styles.windowChips}>
            {DYNO_ANALYSIS_WINDOWS_MS.map((windowMs) => (
              <button
                type="button"
                key={windowMs}
                className={`${styles.windowChip} ${selectedWindows.includes(windowMs) ? styles.windowChipActive : ''}`}
                onClick={() => toggleWindow(windowMs)}
                aria-pressed={selectedWindows.includes(windowMs)}
              >
                <span className={styles.windowDot} style={{ backgroundColor: WINDOW_COLORS[windowMs] }} />
                {windowMs} ms{windowMs === RECOMMENDED_DYNO_WINDOW_MS ? ' · recommended' : ''}
              </button>
            ))}
          </div>
          <div className={styles.quickActions}>
            <button type="button" onClick={() => setSelectedWindows([RECOMMENDED_DYNO_WINDOW_MS])}>Recommended only</button>
            <button type="button" onClick={() => setSelectedWindows([...DYNO_ANALYSIS_WINDOWS_MS])}>Show all</button>
          </div>
        </div>
      </div>

      <div className={styles.chartStack}>
        <AnalysisTimeChart title="Primary RPM" subtitle="16-tooth primary · one-revolution reconstruction" unit="rpm" selected={selectedWindows} traces={primaryRpm} />
        <AnalysisTimeChart title="Secondary RPM" subtitle="12-tooth secondary · one-revolution reconstruction" unit="rpm" selected={selectedWindows} traces={secondaryRpm} />
        <AnalysisTimeChart title="Primary input power" subtitle="CH440 full-throttle torque curve evaluated at measured primary RPM" unit="kW" selected={selectedWindows} traces={primaryPower} yMin={0} yMax={8} />
        <AnalysisTimeChart title="Secondary inertial output power" subtitle="P = J(ω₂² − ω₁²) / (2Δt) · 100 ms uncertainty is available on hover" unit="kW" selected={selectedWindows} traces={secondaryPower} yMin={-10} yMax={10} />
        <AnalysisTimeChart title="CVT speed ratio" subtitle="ωp / ωs from the measured RPM traces" unit="ωp / ωs" selected={selectedWindows} traces={ratio} yMin={0} yMax={6} />
      </div>

      <div className={styles.efficiencyHeading}>
        <div>
          <span className={styles.eyebrow}>Recommended window · 100 ms</span>
          <h2>Estimated transmission efficiency</h2>
          <p>Efficiency uses CH440 input power and positive flywheel energy gain only. RP2040 timing uncertainty and Jₛ = 0.3134–0.3147 kg·m² remain available on hover; no visually misleading filled band is drawn, and no uncertainty is claimed for the assumed CH440 torque curve or unmeasured parasitic losses.</p>
        </div>
      </div>

      <div className={styles.chartStack}>
        <RecommendedTimeChart title="Efficiency vs time" unit="%" trace={recommended.efficiencyPct} yMin={0} yMax={100} />
        <EfficiencyRatioChart points={recommended.efficiencyVsRatio} />
      </div>
    </section>
  );
}
