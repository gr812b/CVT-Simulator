import type { Graph2DProps } from "@components/graph2D/graph2D";
import type { RunResponse } from "@utils/api";
import type { BaseUnitType } from "@utils/unitConversion";
import { UNIT_PRESETS, getTargetUnit } from "@utils/unitConversion";

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



// Mapping from accessor to unit type
export const accessorToUnit = new Map<AccessorStrategy, BaseUnitType>([
    [timeAccessor, 'time'],
    [positionAccessor, 'distance'],
    [velocityAccessor, 'velocity'],
    [accelerationAccessor, 'acceleration'],
    [cvtRatioAccessor, 'dimensionless'],
    [engineRpmAccessor, 'angular_velocity'],
    [engineTorqueAccessor, 'torque'],
]);

// Helper function to get unit label for an accessor
function getAxisUnit(accessor: AccessorStrategy): string {
    const unitType = accessorToUnit.get(accessor);
    if (!unitType) return 'No unit associated with accessor!';
    
    // Get BAJA unit as default
    const unit = getTargetUnit(unitType, UNIT_PRESETS.BAJA);
    return unit || '';
}

export const graphConfigs: GraphConfig[] = [
    {
        xAccessor: timeAccessor,
        yAccessor: [positionAccessor],
        config: {
            title: "Position vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Position", type: "value", unit: getAxisUnit(positionAccessor) },
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
          xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
          yAxis: { name: "Velocity", type: "value", unit: getAxisUnit(velocityAccessor) },
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
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Acceleration", type: "value", unit: getAxisUnit(accelerationAccessor) },
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
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "CVT Ratio", type: "value", unit: getAxisUnit(cvtRatioAccessor) },
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
            xAxis: { name: "Vehicle Speed", type: "value", unit: getAxisUnit(velocityAccessor) },
            yAxis: { name: "Engine RPM", type: "value", unit: getAxisUnit(engineRpmAccessor) },
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
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Engine Torque", type: "value", unit: getAxisUnit(engineTorqueAccessor) },
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