import type { Graph2DProps } from "@components/graph2D/graph2D";
import type { RunResponse } from "@utils/api";

type DataPoint = RunResponse['data'][number]; // TODO: Move to somewhere else (maybe replay controller file)

type AccessorStrategy = (point: DataPoint) => number;

type GraphConfig = Omit<Graph2DProps, 'xData' | 'yData' | 'className'> & {
    xAccessor: AccessorStrategy;
    yAccessor: AccessorStrategy[];
};

export const timeAccessor: AccessorStrategy = (point) => point.time;
const positionAccessor: AccessorStrategy = (point) => point.state.car_position;
const velocityAccessor: AccessorStrategy = (point) => point.state.car_velocity;
const accelerationAccessor: AccessorStrategy = (point) => point.car_state.acceleration;
const cvtRatioAccessor: AccessorStrategy = (point) => point.cvt_state.cvt_ratio;
const engineRpmAccessor: AccessorStrategy = (point) => point.car_state.engine_forces.angular_velocity;
const engineTorqueAccessor: AccessorStrategy = (point) => point.car_state.engine_forces.torque;
const primaryRadialForceAccessor: AccessorStrategy = (point) => point.cvt_state.primaryRadialForce.net;
const secondaryRadialForceAccessor: AccessorStrategy = (point) => point.cvt_state.secondaryRadialForce.net;

export const graphConfigs: GraphConfig[] = [
    {
        xAccessor: timeAccessor,
        yAccessor: [positionAccessor],
        config: {
            title: "Position vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Position", type: "value", unit: "m" },
            height: 400,
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [velocityAccessor],
        config: {
          title: "Velocity vs Time",
          xAxis: { name: "Time", type: "value", unit: "s" },
          yAxis: { name: "Velocity", type: "value", unit: "m/s" },
          height: 400,
          showXLine: true,
          showYLine: true
        }
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [accelerationAccessor],
        config: {
            title: "Acceleration vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Acceleration", type: "value", unit: "m/s²" },
            height: 400,
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [cvtRatioAccessor],
        config: {
            title: "CVT Ratio vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "CVT Ratio", type: "value", unit: "ratio" },
            height: 400,
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: velocityAccessor,
        yAccessor: [engineRpmAccessor],
        config: {
            title: "Shift Curve (Engine RPM vs Vehicle Speed)",
            xAxis: { name: "Vehicle Speed", type: "value", unit: "m/s" },
            yAxis: { name: "Engine RPM", type: "value", unit: "rad/s" },
            height: 400,
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [engineTorqueAccessor],
        config: {
            title: "Engine Torque vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Engine Torque", type: "value", unit: "Nm" },
            height: 400,
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [primaryRadialForceAccessor, secondaryRadialForceAccessor],
        config: {
            title: "Pulley Radial Forces vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Radial Force", type: "value", unit: "N" },
            height: 400,
            showXLine: true,
            showYLine: false
        }
    },
        {
        xAccessor: timeAccessor,
        yAccessor: [secondaryRadialForceAccessor, primaryRadialForceAccessor],
        config: {
            title: "Pulley Radial Forces vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Radial Force", type: "value", unit: "N" },
            height: 400,
            showXLine: true,
            showYLine: false
        }
    }
];