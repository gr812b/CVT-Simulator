import type { Graph2DProps } from '@components/graph2D/graph2D';
import type { ChartConfig } from '@components/graph2D/chartOptions';
import type { ReportColumn, ReportTable } from '@api/client';
import {
  defaultDisplayUnit,
  isQuantityDimension,
  siToDisplay,
} from '@utils/units';

type Series = { key: string; label: string };
type Chart = {
  title: string;
  x: string;
  xLabel: string;
  yLabel: string;
  series: Series[];
  required?: string;
};

export type GraphCategory = {
  title: string;
  graphs: Array<Omit<Graph2DProps, 'replayController'>>;
};

/**
 * This page owns the visual chart declarations. Each key is a CINDER report
 * column; no parameter aliases, nested-result walking, or global graph
 * accessor registry remains in the frontend.
 */
const CHARTS: Array<{ category: string; chart: Chart }> = [
  {
    category: 'Kinematics',
    chart: {
      title: 'Distance travelled',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Position',
      series: [{ key: 'vehicle.distance', label: 'Position' }],
    },
  },
  {
    category: 'Kinematics',
    chart: {
      title: 'Vehicle speed',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Velocity',
      series: [{ key: 'vehicle.speed', label: 'Velocity' }],
    },
  },
  {
    category: 'Kinematics',
    chart: {
      title: 'Vehicle acceleration',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Acceleration',
      series: [{ key: 'vehicle.acceleration', label: 'Acceleration' }],
    },
  },
  {
    category: 'External Load',
    chart: {
      title: 'Road-load forces',
      x: 'vehicle.speed',
      xLabel: 'Vehicle Speed',
      yLabel: 'Force',
      series: [
        { key: 'vehicle.road_force', label: 'Total (Car)' },
        {
          key: 'vehicle.rolling_resistance_force',
          label: 'Rolling Resistance',
        },
        { key: 'vehicle.grade_force', label: 'Incline Force' },
        { key: 'vehicle.aerodynamic_force', label: 'Air Resistance' },
      ],
    },
  },
  {
    category: 'CVT Ratio',
    chart: {
      title: 'CVT ratio',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'CVT Ratio',
      series: [
        {
          key: 'geometry.effective_ratio_secondary_over_primary',
          label: 'CVT Ratio',
        },
      ],
    },
  },
  {
    category: 'CVT Ratio',
    chart: {
      title: 'Ratio rate',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'CVT Ratio Rate of Change',
      series: [{ key: 'geometry.effective_ratio_rate', label: 'Ratio Rate' }],
    },
  },
  {
    category: 'CVT Ratio',
    chart: {
      title: 'Primary and secondary radius rates',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Radius Rate',
      series: [
        {
          key: 'geometry.primary_outer_radius_rate',
          label: 'Primary Radius Rate',
        },
        {
          key: 'geometry.secondary_outer_radius_rate',
          label: 'Secondary Radius Rate',
        },
      ],
    },
  },
  {
    category: 'CVT Ratio',
    chart: {
      title: 'Shift curve',
      x: 'vehicle.speed',
      xLabel: 'Vehicle Speed',
      yLabel: 'Engine RPM',
      series: [{ key: 'state.primary_angular_speed', label: 'Engine RPM' }],
    },
  },
  {
    category: 'Engine',
    chart: {
      title: 'Engine speed',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Engine RPM',
      series: [{ key: 'state.primary_angular_speed', label: 'Engine RPM' }],
    },
  },
  {
    category: 'Engine',
    chart: {
      title: 'Engine torque',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Engine Torque',
      series: [
        { key: 'boundary.primary_external_torque', label: 'Engine Torque' },
      ],
    },
  },
  {
    category: 'Engine',
    chart: {
      title: 'Engine power',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Engine Power',
      series: [
        { key: 'observer.primary_boundary_power', label: 'Engine Power' },
      ],
    },
  },
  {
    category: 'Primary Pulley',
    chart: {
      title: 'Primary belt-normal load',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Total normal load (both faces)',
      series: [
        { key: 'contact.primary_normal_resultant', label: 'Normal load' },
      ],
    },
  },
  {
    category: 'Secondary Pulley',
    chart: {
      title: 'Secondary belt-normal load',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Total normal load (both faces)',
      series: [
        { key: 'contact.secondary_normal_resultant', label: 'Normal load' },
      ],
    },
  },
  {
    category: 'Belt Tension',
    chart: {
      title: 'Belt tensions',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Tension',
      series: [
        { key: 'contact.primary_tension_in', label: 'Primary In' },
        { key: 'contact.primary_tension_out', label: 'Primary Out' },
        { key: 'contact.secondary_tension_in', label: 'Secondary In' },
        { key: 'contact.secondary_tension_out', label: 'Secondary Out' },
      ],
    },
  },
  {
    category: 'Slip Model',
    chart: {
      title: 'Relative belt speed',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Relative Velocity',
      series: [
        {
          key: 'contact.primary_relative_speed',
          label: 'Primary Relative Velocity',
        },
        {
          key: 'contact.secondary_relative_speed',
          label: 'Secondary Relative Velocity',
        },
      ],
    },
  },
  {
    category: 'Slip Model',
    chart: {
      title: 'Belt speed',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Belt Speed',
      series: [{ key: 'state.belt_speed', label: 'Belt Speed' }],
    },
  },
  {
    category: 'Slip Model',
    chart: {
      title: 'Transmitted torques',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Torque',
      series: [
        { key: 'contact.primary_transmitted_torque', label: 'Primary Torque' },
        {
          key: 'contact.secondary_transmitted_torque',
          label: 'Secondary Torque',
        },
      ],
    },
  },
  {
    category: 'Simulation Mode',
    chart: {
      title: 'Traction utilization',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Traction utilization λ',
      series: [
        { key: 'contact.primary_lambda', label: 'Primary λ' },
        { key: 'contact.secondary_lambda', label: 'Secondary λ' },
      ],
    },
  },
  {
    category: 'Primary Pulley',
    chart: {
      title: 'Primary axial force balance',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Force',
      required: 'balance.primary.belt_axial_force',
      series: [
        { key: 'balance.primary.belt_axial_force', label: 'Belt (axial)' },
        { key: 'balance.primary.axial_spring_force', label: 'Axial spring' },
        {
          key: 'balance.primary.mechanism_force',
          label: 'Flyweights / mechanisms',
        },
        { key: 'balance.primary.stop_force', label: 'Travel stop' },
        {
          key: 'balance.primary.axial_inertia_force',
          label: 'Mass × acceleration',
        },
      ],
    },
  },
  {
    category: 'Primary Pulley',
    chart: {
      title: 'Primary torque balance',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Torque',
      required: 'balance.primary.inertia_torque',
      series: [
        { key: 'boundary.primary_external_torque', label: 'Boundary' },
        { key: 'balance.primary.belt_torque', label: 'Belt' },
        { key: 'balance.primary.coupling_torque', label: 'Mechanism coupling' },
        {
          key: 'balance.primary.inertia_torque',
          label: 'Inertia × acceleration',
        },
      ],
    },
  },
  {
    category: 'Primary Pulley',
    chart: {
      title: 'Primary angular acceleration',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Angular acceleration',
      series: [
        {
          key: 'balance.primary.angular_acceleration',
          label: 'Angular acceleration',
        },
      ],
    },
  },
  {
    category: 'Primary Pulley',
    chart: {
      title: 'Primary actuator forces',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Force',
      series: [
        { key: 'actuation.primary.axial_spring', label: 'Axial spring' },
        { key: 'actuation.primary.total_clamp_force', label: 'Total' },
      ],
    },
  },
  {
    category: 'Secondary Pulley',
    chart: {
      title: 'Secondary axial force balance',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Force',
      required: 'balance.secondary.belt_axial_force',
      series: [
        { key: 'balance.secondary.belt_axial_force', label: 'Belt (axial)' },
        { key: 'balance.secondary.axial_spring_force', label: 'Axial spring' },
        {
          key: 'balance.secondary.mechanism_force',
          label: 'Helix / mechanisms',
        },
        { key: 'balance.secondary.stop_force', label: 'Travel stop' },
        {
          key: 'balance.secondary.axial_inertia_force',
          label: 'Mass × acceleration',
        },
      ],
    },
  },
  {
    category: 'Secondary Pulley',
    chart: {
      title: 'Secondary torque balance',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Torque',
      required: 'balance.secondary.inertia_torque',
      series: [
        { key: 'boundary.secondary_external_torque', label: 'Boundary' },
        { key: 'balance.secondary.belt_torque', label: 'Belt' },
        {
          key: 'balance.secondary.coupling_torque',
          label: 'Mechanism coupling',
        },
        {
          key: 'balance.secondary.inertia_torque',
          label: 'Inertia × acceleration',
        },
      ],
    },
  },
  {
    category: 'Secondary Pulley',
    chart: {
      title: 'Secondary angular acceleration',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Angular acceleration',
      series: [
        {
          key: 'balance.secondary.angular_acceleration',
          label: 'Angular acceleration',
        },
      ],
    },
  },
  {
    category: 'Secondary Pulley',
    chart: {
      title: 'Secondary actuator forces',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Force',
      series: [
        { key: 'actuation.secondary.axial_spring', label: 'Axial spring' },
        { key: 'actuation.secondary.total_clamp_force', label: 'Total' },
      ],
    },
  },
  {
    category: 'Primary Pulley',
    chart: {
      title: 'Primary flyweight forces',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Force',
      series: [
        {
          key: 'actuation.primary.fixed_pivot_flyweight_centrifugal',
          label: 'Centrifugal',
        },
        {
          key: 'actuation.primary.fixed_pivot_flyweight_axial_inertia',
          label: 'Axial inertia',
        },
        {
          key: 'actuation.primary.fixed_pivot_flyweight_motion_ratio_curvature',
          label: 'Motion curvature',
        },
      ],
    },
  },
  {
    category: 'Secondary Pulley',
    chart: {
      title: 'Secondary helix forces',
      x: 'time_s',
      xLabel: 'Time',
      yLabel: 'Force',
      series: [
        {
          key: 'actuation.secondary.helix_reacted_belt_torque_force',
          label: 'Belt torque',
        },
        {
          key: 'actuation.secondary.helix_shaft_acceleration_force',
          label: 'Shaft acceleration',
        },
        {
          key: 'actuation.secondary.helix_shift_acceleration_force',
          label: 'Shift acceleration',
        },
        {
          key: 'actuation.secondary.helix_shift_speed_curvature_force',
          label: 'Shift curvature',
        },
        {
          key: 'actuation.secondary.helix_torsional_preload',
          label: 'Torsional spring',
        },
      ],
    },
  },
];

function column(table: ReportTable, key: string): ReportColumn | undefined {
  return table.columns.find((candidate) => candidate.key === key);
}

type ChartValue = number | null;

/**
 * A report gap must stay a gap. Carrying the prior value forward makes an
 * unavailable signal look valid and can conceal a reporting or solver issue.
 */
function shown(columnValue: ReportColumn): ChartValue[] {
  return columnValue.values.map((value) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return null;
    return isQuantityDimension(columnValue.dimension)
      ? siToDisplay(value, defaultDisplayUnit(columnValue.dimension))
      : value;
  });
}

function shownXAxis(columnValue: ReportColumn): number[] | null {
  const values = shown(columnValue);
  return values.every((value): value is number => value !== null)
    ? values
    : null;
}

function unit(columnValue: ReportColumn): string {
  return isQuantityDimension(columnValue.dimension)
    ? defaultDisplayUnit(columnValue.dimension)
    : columnValue.canonical_unit;
}

export function buildReportGraphs(table: ReportTable): GraphCategory[] {
  const categories = new Map<string, GraphCategory>();

  CHARTS.forEach(({ category, chart }) => {
    if (chart.required && !column(table, chart.required)) return;
    const x = column(table, chart.x);
    const y = chart.series
      .map((series) => ({ series, column: column(table, series.key) }))
      .filter(
        (entry): entry is { series: Series; column: ReportColumn } =>
          entry.column !== undefined,
      );
    if (!x || y.length === 0) return;

    const yAxis = y[0].column;
    const config: ChartConfig = {
      title: chart.title,
      xAxis: { name: chart.xLabel, type: 'value', unit: unit(x) },
      yAxis: { name: chart.yLabel, type: 'value', unit: unit(yAxis) },
      seriesNames: y.map((entry) => entry.series.label),
      showXLine: true,
      showYLine: false,
    };
    const xData = shownXAxis(x);
    if (xData === null) return;
    const seriesData = y.map((entry) => shown(entry.column));
    const graph = {
      xData,
      yData: xData.map((_, index) =>
        seriesData.map((values) => values[index] ?? null),
      ),
      config,
    };
    const existing = categories.get(category) ?? {
      title: category,
      graphs: [],
    };
    existing.graphs.push(graph);
    categories.set(category, existing);
  });

  return [...categories.values()];
}
