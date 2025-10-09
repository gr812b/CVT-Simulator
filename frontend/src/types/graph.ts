import type { Graph2DProps } from "@components/graph2D/graph2D";
import type { RunResponse } from "@utils/api";

type DataPoint = RunResponse['data'][number]; // TODO: Move to somewhere else (maybe replay controller file)

type GraphConfig = Omit<Graph2DProps, 'xData' | 'yData' | 'className'> & {
    xAccessor: (point: DataPoint) => number;
    yAccessor: (point: DataPoint) => number;
};

export const graphConfigs: GraphConfig[] = [
    {
        xAccessor: (point) => point.time,
        yAccessor: (point) => point.state.car_position,
        config: {
            title: "Position vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Position", type: "value", unit: "m" },
            height: 400
        }
    },
    {
        xAccessor: (point) => point.time,
        yAccessor: (point) => point.state.car_velocity,
        config: {
          title: "Velocity vs Time",
          xAxis: { name: "Time", type: "value", unit: "s" },
          yAxis: { name: "Velocity", type: "value", unit: "m/s" },
          height: 400
        }
    },
    {
        xAccessor: (point) => point.time,
        yAccessor: (point) => point.car_state.acceleration,
        config: {
            title: "Acceleration vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Acceleration", type: "value", unit: "m/s²" },
            height: 400
        }
    },
    {
        xAccessor: (point) => point.time,
        yAccessor: (point) => point.cvt_state.cvt_ratio,
        config: {
            title: "CVT Ratio vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "CVT Ratio", type: "value", unit: "ratio" },
            height: 400
        }
    },
    {
        xAccessor: (point) => point.state.car_velocity,
        yAccessor: (point) => point.car_state.engine_forces.angular_velocity,
        config: {
            title: "Shift Curve (Engine RPM vs Vehicle Speed)",
            xAxis: { name: "Vehicle Speed", type: "value", unit: "m/s" },
            yAxis: { name: "Engine RPM", type: "value", unit: "rad/s" },
            height: 400
        }
    },
    {
        xAccessor: (point) => point.time,
        yAccessor: (point) => point.car_state.engine_forces.torque,
        config: {
            title: "Engine Torque vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Engine Torque", type: "value", unit: "Nm" },
            height: 400
        }
    }
];