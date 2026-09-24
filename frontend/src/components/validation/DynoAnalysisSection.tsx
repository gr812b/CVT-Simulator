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

function rgba(hex: string, alpha: number): string {
  if (/^#[0-9a-fA-F]{6}$/.test(hex)) {
    const value = Number.parseInt(hex.slice(1), 16);
    const r = (value >> 16) & 255;
    const g = (value >> 8) & 255;
    const b = value & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  return `color-mix(in srgb, ${hex} ${Math.round(alpha * 100)}%, transparent)`;
}

function formatNumber(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 1000) return value.toFixed(0);
  if (magnitude >= 100) return value.toFixed(1);
  if (magnitude >= 10) return value.toFixed(2);
  return value.toFixed(3);
}

function pointBounds(point: DynoTracePoint): [number, number] | null {
  if (typeof point.lower === 'number' && Number.isFinite(point.lower) && typeof point.upper === 'number' && Number.isFinite(point.upper)) {
    return [point.lower, point.upper];
  }
  if (typeof point.uncertainty === 'number' && Number.isFinite(point.uncertainty)) {
    return [point.value - point.uncertainty, point.value + point.uncertainty];
  }
  return null;
}

function traceSeries(
  selected: DynoAnalysisWindowMs[],
  traces: Record<DynoAnalysisWindowMs, DynoTracePoint[]>,
): Record<string, unknown>[] {
  const series: Record<string, unknown>[] = [];
  for (const windowMs of selected) {
    const color = WINDOW_COLORS[windowMs];
    const trace = traces[windowMs];
    if (windowMs === RECOMMENDED_DYNO_WINDOW_MS) {
      const bounded = trace.filter((point) => pointBounds(point) !== null);
      if (bounded.length > 0) {
        series.push(
          {
            name: '__uncertainty_floor',
            type: 'line',
            stack: '__recommended_uncertainty',
            symbol: 'none',
            silent: true,
            tooltip: { show: false },
            lineStyle: { opacity: 0 },
            areaStyle: { opacity: 0 },
            data: bounded.map((point) => [point.timeS, pointBounds(point)?.[0] ?? point.value]),
          },
          {
            name: '100 ms uncertainty',
            type: 'line',
            stack: '__recommended_uncertainty',
            symbol: 'none',
            silent: true,
            tooltip: { show: false },
            lineStyle: { opacity: 0 },
            areaStyle: { color: rgba(color, 0.20), opacity: 1 },
            data: bounded.map((point) => {
              const bounds = pointBounds(point);
              return [point.timeS, bounds === null ? 0 : bounds[1] - bounds[0]];
            }),
          },
        );
      }
    }
    series.push({
      name: `${windowMs} ms`,
      type: 'line',
      symbol: 'none',
      showSymbol: false,
      lineStyle: { color, width: windowMs === RECOMMENDED_DYNO_WINDOW_MS ? 2.6 : 1.6, opacity: 0.92 },
      itemStyle: { color },
      emphasis: { focus: 'series' },
      data: trace.map((point) => [point.timeS, point.value]),
    });
  }
  return series;
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
        valueFormatter: (value: unknown) => typeof value === 'number' ? `${formatNumber(value)} ${unit}` : String(value ?? '—'),
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
      grid: { left: 74, right: 32, top: 42, bottom: 62, containLabel: true },
      xAxis: {
        type: 'value',
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
  }, [selected, traces, unit, yMax, yMin]);

  return (
    <article className={styles.chartCard}>
      <div className={styles.chartHeading}>
        <div>
          <h3>{title}</h3>
          {subtitle !== undefined && <p>{subtitle}</p>}
        </div>
      </div>
      <ReactECharts option={option} className={styles.chart} notMerge />
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

function median(values: number[]): number | null {
  const finite = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (finite.length === 0) return null;
  const middle = Math.floor(finite.length / 2);
  return finite.length % 2 === 0 ? 0.5 * (finite[middle - 1] + finite[middle]) : finite[middle];
}

function binnedEfficiency(points: EfficiencyRatioPoint[]): Array<{ ratio: number; efficiency: number; lower: number; upper: number }> {
  const minRatio = 1;
  const maxRatio = 6;
  const bins = 16;
  const width = (maxRatio - minRatio) / bins;
  const output: Array<{ ratio: number; efficiency: number; lower: number; upper: number }> = [];
  for (let bin = 0; bin < bins; bin += 1) {
    const left = minRatio + bin * width;
    const right = left + width;
    const inside = points.filter((point) => point.ratio >= left && point.ratio < right && point.efficiencyPct >= 0 && point.efficiencyPct <= 120);
    if (inside.length < 2) continue;
    const ratio = median(inside.map((point) => point.ratio));
    const efficiency = median(inside.map((point) => point.efficiencyPct));
    const lower = median(inside.map((point) => point.lowerPct));
    const upper = median(inside.map((point) => point.upperPct));
    if (ratio === null || efficiency === null || lower === null || upper === null) continue;
    output.push({ ratio, efficiency, lower, upper });
  }
  return output;
}

function EfficiencyRatioChart({ points }: { points: EfficiencyRatioPoint[] }) {
  const option = useMemo<EChartsOption>(() => {
    const text = cssColor('--text-color', '#f4f4f5');
    const grid = cssColor('--grid-color', '#404040');
    const primary = cssColor('--primary', '#bb0808');
    const tooltipBackground = cssColor('--tooltip-bg', '#202124');
    const filtered = points.filter((point) => point.ratio >= 1 && point.ratio <= 6 && point.efficiencyPct >= 0 && point.efficiencyPct <= 120);
    const trend = binnedEfficiency(filtered);
    const bandColor = '#a78bfa';
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
          if (!Array.isArray(data) || typeof data[0] !== 'number' || typeof data[1] !== 'number') return '';
          return `<strong>Ratio ${data[0].toFixed(3)}</strong><br/>Efficiency: ${data[1].toFixed(1)}%`;
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
          symbolSize: 5,
          itemStyle: { color: bandColor, opacity: 0.5 },
          data: filtered.map((point) => [point.ratio, point.efficiencyPct]),
        },
        {
          name: '__band_floor',
          type: 'line',
          stack: '__ratio_band',
          silent: true,
          symbol: 'none',
          tooltip: { show: false },
          lineStyle: { opacity: 0 },
          areaStyle: { opacity: 0 },
          data: trend.map((point) => [point.ratio, point.lower]),
        },
        {
          name: 'Timing + inertia range',
          type: 'line',
          stack: '__ratio_band',
          silent: true,
          symbol: 'none',
          tooltip: { show: false },
          lineStyle: { opacity: 0 },
          areaStyle: { color: rgba(bandColor, 0.22), opacity: 1 },
          data: trend.map((point) => [point.ratio, Math.max(0, point.upper - point.lower)]),
        },
        {
          name: 'Binned median',
          type: 'line',
          symbol: 'none',
          lineStyle: { color: bandColor, width: 2.8 },
          data: trend.map((point) => [point.ratio, point.efficiency]),
        },
      ],
    };
  }, [points]);

  return (
    <article className={styles.chartCard}>
      <div className={styles.chartHeading}>
        <div>
          <h3>Efficiency vs speed ratio</h3>
          <p>100 ms recommended window · shaded band includes RP2040 timing and the secondary-inertia bracket.</p>
        </div>
      </div>
      <ReactECharts option={option} className={styles.chart} notMerge />
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
        <AnalysisTimeChart title="Secondary inertial output power" subtitle="P = J(ω₂² − ω₁²) / (2Δt) · shaded 100 ms band includes timing + inertia range" unit="kW" selected={selectedWindows} traces={secondaryPower} yMin={-10} yMax={10} />
        <AnalysisTimeChart title="CVT speed ratio" subtitle="ωp / ωs from the measured RPM traces" unit="ωp / ωs" selected={selectedWindows} traces={ratio} yMin={0} yMax={6} />
      </div>

      <div className={styles.efficiencyHeading}>
        <div>
          <span className={styles.eyebrow}>Recommended window · 100 ms</span>
          <h2>Estimated transmission efficiency</h2>
          <p>Efficiency uses CH440 input power and positive flywheel energy gain only. The shaded region includes RP2040 timing uncertainty and Jₛ = 0.3134–0.3147 kg·m²; it does not claim uncertainty in the assumed CH440 torque curve or unmeasured parasitic losses.</p>
        </div>
      </div>

      <div className={styles.chartStack}>
        <RecommendedTimeChart title="Efficiency vs time" unit="%" trace={recommended.efficiencyPct} yMin={0} yMax={100} />
        <EfficiencyRatioChart points={recommended.efficiencyVsRatio} />
      </div>
    </section>
  );
}
