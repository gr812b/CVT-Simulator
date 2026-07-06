import type { Graph2DProps } from '@components/graph2D/graph2D';
import { TooltipPosition, type ChartConfig } from '@components/graph2D/chartOptions';
import type { ReportColumn, ReportTable } from '@api/client';
import { defaultDisplayUnit, isQuantityDimension, siToDisplay } from '@utils/units';

type Series = { key: string; label: string };
type Chart = {
  title: string;
  x: string;
  xLabel: string;
  yLabel: string;
  series: Series[];
  tooltip: TooltipPosition;
};

export type GraphCategory = { title: string; graphs: Array<Omit<Graph2DProps, 'replayController'>> };

/**
 * This page owns the visual chart declarations. Each key is a CINDER report
 * column; no parameter aliases, nested-result walking, or global graph
 * accessor registry remains in the frontend.
 */
const CHARTS: Array<{ category: string; chart: Chart }> = [
  { category: 'Kinematics', chart: { title: 'Position vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Position', series: [{ key: 'vehicle.distance', label: 'Position' }], tooltip: TooltipPosition.TopLeft } },
  { category: 'Kinematics', chart: { title: 'Velocity vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Velocity', series: [{ key: 'vehicle.speed', label: 'Velocity' }], tooltip: TooltipPosition.BottomRight } },
  { category: 'Kinematics', chart: { title: 'Acceleration vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Acceleration', series: [{ key: 'vehicle.acceleration', label: 'Acceleration' }], tooltip: TooltipPosition.TopRight } },
  { category: 'Acceleration of Engine and Car', chart: { title: 'Torques at Wheels vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Torque', series: [{ key: 'contact.secondary_transmitted_torque', label: 'Secondary Torque' }, { key: 'boundary.output_external_torque', label: 'Load Torque at Secondary' }], tooltip: TooltipPosition.TopRight } },
  { category: 'Acceleration of Engine and Car', chart: { title: 'Torques at Engine vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Torque', series: [{ key: 'contact.primary_transmitted_torque', label: 'Primary Torque' }, { key: 'boundary.engine_torque', label: 'Engine Torque' }], tooltip: TooltipPosition.TopRight } },
  { category: 'External Load', chart: { title: 'External Load Forces at Car vs Vehicle Speed', x: 'vehicle.speed', xLabel: 'Vehicle Speed', yLabel: 'Force', series: [{ key: 'vehicle.road_force', label: 'Total (Car)' }, { key: 'vehicle.rolling_resistance_force', label: 'Rolling Resistance' }, { key: 'vehicle.grade_force', label: 'Incline Force' }, { key: 'vehicle.aerodynamic_force', label: 'Air Resistance' }], tooltip: TooltipPosition.TopLeft } },
  { category: 'CVT Ratio', chart: { title: 'CVT Ratio vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'CVT Ratio', series: [{ key: 'geometry.effective_ratio_secondary_over_primary', label: 'CVT Ratio' }], tooltip: TooltipPosition.TopRight } },
  { category: 'CVT Ratio', chart: { title: 'CVT Ratio Rate of Change vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'CVT Ratio Rate of Change', series: [{ key: 'geometry.effective_ratio_rate', label: 'Ratio Rate' }], tooltip: TooltipPosition.BottomRight } },
  { category: 'CVT Ratio', chart: { title: 'Primary and Secondary Outer Radius Rate vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Radius Rate', series: [{ key: 'geometry.primary_outer_radius_rate', label: 'Primary Radius Rate' }, { key: 'geometry.secondary_outer_radius_rate', label: 'Secondary Radius Rate' }], tooltip: TooltipPosition.BottomRight } },
  { category: 'CVT Ratio', chart: { title: 'Shift Curve (Engine RPM vs Vehicle Speed)', x: 'vehicle.speed', xLabel: 'Vehicle Speed', yLabel: 'Engine RPM', series: [{ key: 'state.primary_angular_speed', label: 'Engine RPM' }], tooltip: TooltipPosition.BottomRight } },
  { category: 'Engine', chart: { title: 'Engine RPM vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Engine RPM', series: [{ key: 'state.primary_angular_speed', label: 'Engine RPM' }], tooltip: TooltipPosition.BottomRight } },
  { category: 'Engine', chart: { title: 'Engine Torque vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Engine Torque', series: [{ key: 'boundary.engine_torque', label: 'Engine Torque' }], tooltip: TooltipPosition.TopRight } },
  { category: 'Engine', chart: { title: 'Engine Power vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Engine Power', series: [{ key: 'observer.engine_power', label: 'Engine Power' }], tooltip: TooltipPosition.TopRight } },
  { category: 'Primary Pulley', chart: { title: 'Primary Axial Forces vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Force', series: [{ key: 'actuation.primary.total_clamp_force', label: 'Primary Clamp' }, { key: 'contact.primary_normal_resultant', label: 'Primary Belt Force' }], tooltip: TooltipPosition.TopRight } },
  { category: 'Secondary Pulley', chart: { title: 'Secondary Axial Forces vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Force', series: [{ key: 'actuation.secondary.total_clamp_force', label: 'Secondary Clamp' }, { key: 'contact.secondary_normal_resultant', label: 'Secondary Belt Force' }], tooltip: TooltipPosition.TopRight } },
  { category: 'Slip Model', chart: { title: 'Primary and Secondary Relative Velocity vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Relative Velocity', series: [{ key: 'contact.primary_relative_speed', label: 'Primary Relative Velocity' }, { key: 'contact.secondary_relative_speed', label: 'Secondary Relative Velocity' }], tooltip: TooltipPosition.TopRight } },
  { category: 'Slip Model', chart: { title: 'Belt Speed vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Belt Speed', series: [{ key: 'state.belt_speed', label: 'Belt Speed' }], tooltip: TooltipPosition.TopRight } },
  { category: 'Slip Model', chart: { title: 'Primary and Secondary Torque vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Torque', series: [{ key: 'contact.primary_transmitted_torque', label: 'Primary Torque' }, { key: 'contact.secondary_transmitted_torque', label: 'Secondary Torque' }], tooltip: TooltipPosition.BottomRight } },
  { category: 'Simulation Mode', chart: { title: 'Slip Branch State vs Time', x: 'time_s', xLabel: 'Time', yLabel: 'Branch Active', series: [{ key: 'contact.primary_lambda', label: 'Primary λ' }, { key: 'contact.secondary_lambda', label: 'Secondary λ' }], tooltip: TooltipPosition.BottomRight } },
];

function column(table: ReportTable, key: string): ReportColumn | undefined {
  return table.columns.find((candidate) => candidate.key === key);
}

function shown(columnValue: ReportColumn): number[] {
  let lastFinite = 0;
  return columnValue.values.map((value) => {
    const finite = typeof value === 'number' && Number.isFinite(value) ? value : lastFinite;
    lastFinite = finite;
    return isQuantityDimension(columnValue.dimension)
      ? siToDisplay(finite, defaultDisplayUnit(columnValue.dimension))
      : finite;
  });
}

function unit(columnValue: ReportColumn): string {
  return isQuantityDimension(columnValue.dimension)
    ? defaultDisplayUnit(columnValue.dimension)
    : columnValue.canonicalUnit;
}

export function buildReportGraphs(table: ReportTable): GraphCategory[] {
  const categories = new Map<string, GraphCategory>();

  CHARTS.forEach(({ category, chart }) => {
    const x = column(table, chart.x);
    const y = chart.series
      .map((series) => ({ series, column: column(table, series.key) }))
      .filter((entry): entry is { series: Series; column: ReportColumn } => entry.column !== undefined);
    if (!x || y.length === 0) return;

    const yAxis = y[0].column;
    const config: ChartConfig = {
      title: chart.title,
      xAxis: { name: chart.xLabel, type: 'value', unit: unit(x) },
      yAxis: { name: chart.yLabel, type: 'value', unit: unit(yAxis) },
      seriesNames: y.map((entry) => entry.series.label),
      showXLine: true,
      showYLine: false,
      tooltipPosition: chart.tooltip,
    };
    const xData = shown(x);
    const seriesData = y.map((entry) => shown(entry.column));
    const graph = {
      xData,
      yData: xData.map((_, index) => seriesData.map((values) => values[index] ?? 0)),
      config,
    };
    const existing = categories.get(category) ?? { title: category, graphs: [] };
    existing.graphs.push(graph);
    categories.set(category, existing);
  });

  return [...categories.values()];
}
