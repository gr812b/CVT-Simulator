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
// Accessor for flyweightForce.net
const primaryFlyweightForceAccessor: AccessorStrategy = (point) => {
    const prf = point.cvt_state.primaryRadialForce;
    const pulleyForce = prf.pulleyForce;
    if (!pulleyForce) return 0;
    if ('flyweightForce' in pulleyForce && pulleyForce.flyweightForce) {
        return pulleyForce.flyweightForce.net;
    }
    return 0;
};

// Accessor for springForce.net or springCompForce.net
const primarySpringForceAccessor: AccessorStrategy = (point) => {
    const prf = point.cvt_state.primaryRadialForce;
    const pulleyForce = prf.pulleyForce;
    if (!pulleyForce) return 0;
    if ('springForce' in pulleyForce && pulleyForce.springForce) {
        return pulleyForce.springForce.net;
    }
    if ('springCompForce' in pulleyForce && pulleyForce.springCompForce) {
        return pulleyForce.springCompForce.net;
    }
    return 0;
};



export const graphConfigs: GraphConfig[] = [
    {
        xAccessor: timeAccessor,
        yAccessor: [positionAccessor],
        config: {
            title: "Position vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Position", type: "value", unit: "m" },
            seriesNames: ["Position"],
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
          seriesNames: ["Velocity"],
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
            seriesNames: ["Acceleration"],
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
            seriesNames: ["CVT Ratio"],
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
            seriesNames: ["Engine RPM"],
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
            seriesNames: ["Engine Torque"],
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
            seriesNames: ["Primary ", "Secondary"],
            height: 400,
            showXLine: true,
            showYLine: false
        }
    },
        {
            xAccessor: timeAccessor,
            yAccessor: [primaryRadialForceAccessor, primaryFlyweightForceAccessor, primarySpringForceAccessor],
            config: {
                title: "Primary Forces vs Time",
                xAxis: { name: "Time", type: "value", unit: "s" },
                yAxis: { name: "Primary Force", type: "value", unit: "N" },
                seriesNames: ["Net", "Flyweight", "Spring"],
                height: 400,
            showXLine: true,
            showYLine: false
        }
    }
];