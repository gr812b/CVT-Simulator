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
const accelerationAccessor: AccessorStrategy = (point) => point.system.car.acceleration;
const cvtRatioAccessor: AccessorStrategy = (point) => point.system.cvt.cvt_ratio;
const engineRpmAccessor: AccessorStrategy = (point) => point.system.engine.angular_velocity;
const engineTorqueAccessor: AccessorStrategy = (point) => point.system.engine.torque;
const cvtRatioRateOfChangeAccessor: AccessorStrategy = (point) => point.system.slip.cvt_ratio_derivative;
const enginePowerAccessor: AccessorStrategy = (point) => point.system.engine.power;
const t_maxAccessor: AccessorStrategy = (point) => point.system.slip.t_max;
const t_cAccessor: AccessorStrategy = (point) => point.system.slip.t_c;
const primaryRadialForceAccessor: AccessorStrategy = (point) => point.system.cvt.primaryRadialForce.net;
const primaryForceAccessor: AccessorStrategy = (point) => point.system.cvt.primaryRadialForce.pulleyForce.net;
const secondaryRadialForceAccessor: AccessorStrategy = (point) => point.system.cvt.secondaryRadialForce.net;
const secondaryForceAccessor: AccessorStrategy = (point) => point.system.cvt.secondaryRadialForce.pulleyForce.net;
// Accessor for flyweightForce.net
const primaryFlyweightForceAccessor: AccessorStrategy = (point) => {
    const prf = point.system.cvt.primaryRadialForce;
    const pulleyForce = prf.pulleyForce;
    if (!pulleyForce) return 0;
    if ('flyweightForce' in pulleyForce && pulleyForce.flyweightForce) {
        return pulleyForce.flyweightForce.net;
    }
    return 0;
};

// Accessor for springForce.net or springCompForce.net
const primarySpringForceAccessor: AccessorStrategy = (point) => {
    const prf = point.system.cvt.primaryRadialForce;
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
// dd accorsors for secondary radial force helix 
const secondaryHelixFeedbackTorqueAccessor: AccessorStrategy = (point) => {
    const srf = point.system.cvt.secondaryRadialForce;
    const pulleyForce = srf.pulleyForce;
    if (!pulleyForce) return 0;
    if ('helix_force' in pulleyForce && pulleyForce.helix_force) {
        return pulleyForce.helix_force.feedbackTorque;
    }
    return 0;
};

const secondaryHelixSpringTorqueAccessor: AccessorStrategy = (point) => {
    const srf = point.system.cvt.secondaryRadialForce;
    const pulleyForce = srf.pulleyForce;
    if (!pulleyForce) return 0;
    if ('helix_force' in pulleyForce && pulleyForce.helix_force && pulleyForce.helix_force.springTorque) {
        return pulleyForce.helix_force.springTorque.net;
    }
    return 0;
}; 

const secondaryHelixForceAccessor: AccessorStrategy = (point) => {
    const srf = point.system.cvt.secondaryRadialForce;
    const pulleyForce = srf.pulleyForce;
    if (!pulleyForce) return 0;
    if ('helix_force' in pulleyForce && pulleyForce.helix_force) {
        return pulleyForce.helix_force.net;
    }
    return 0;
};

const secondarySpringCompForceAccessor: AccessorStrategy = (point) => {
    const srf = point.system.cvt.secondaryRadialForce;
    const pulleyForce = srf.pulleyForce;
    if (!pulleyForce) return 0;
    if ('springCompForce' in pulleyForce && pulleyForce.springCompForce) {
        return pulleyForce.springCompForce.net;
    }
    return 0;
}; 

const inclineForceAccessor: AccessorStrategy = (point) => point.system.car.external_forces.incline_force;
const dragForceAccessor: AccessorStrategy = (point) => point.system.car.external_forces.drag_force;
const totalExternalLoadAccessor: AccessorStrategy = (point) => point.system.car.external_forces.net;

// Mapping from accessor to unit type
export const accessorToUnit = new Map<AccessorStrategy, BaseUnitType>([
    [timeAccessor, 'time'],
    [positionAccessor, 'distance'],
    [velocityAccessor, 'velocity'],
    [accelerationAccessor, 'acceleration'],
    [cvtRatioAccessor, 'dimensionless'],
    [engineRpmAccessor, 'angular_velocity'],
    [engineTorqueAccessor, 'torque'],
    [cvtRatioRateOfChangeAccessor, 'dimensionless_rate'],
    [enginePowerAccessor, 'power'],
    [t_cAccessor, 'torque'],
    [t_maxAccessor, 'torque'],
    [primaryRadialForceAccessor, 'force'],
    [secondaryRadialForceAccessor, 'force'],
    [primaryFlyweightForceAccessor, 'force'],
    [primarySpringForceAccessor, 'force'],
    [secondaryHelixFeedbackTorqueAccessor, 'torque'],
    [secondaryHelixSpringTorqueAccessor, 'torque'],
    [secondaryHelixForceAccessor, 'force'],
    [secondarySpringCompForceAccessor, 'force'],
    [primaryForceAccessor, 'force'],
    [secondaryForceAccessor, 'force'],
    [inclineForceAccessor, 'force'],
    [dragForceAccessor, 'force'],
    [totalExternalLoadAccessor, 'force'],
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
    // Just engine rpm vs time
    {
        xAccessor: timeAccessor,
        yAccessor: [engineRpmAccessor],
        config: {
            title: "Engine RPM vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
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
        yAccessor: [enginePowerAccessor],
        config: {
            title: "Engine Power vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Engine Power", type: "value", unit: getAxisUnit(enginePowerAccessor) },
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
        yAccessor: [cvtRatioRateOfChangeAccessor],
        config: {
            title: "CVT Ratio Rate of Change vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "CVT Ratio Rate of Change", type: "value", unit: getAxisUnit(cvtRatioRateOfChangeAccessor) },
            height: 400,
            showXLine: true,
            showYLine: false
        }
    },
        {
            xAccessor: timeAccessor,
            yAccessor: [primaryForceAccessor, primaryFlyweightForceAccessor, primarySpringForceAccessor],
            config: {
                title: "Primary Forces vs Time",
                xAxis: { name: "Time", type: "value", unit: "s" },
                yAxis: { name: "Primary Force", type: "value", unit: "N" },
                seriesNames: ["Net", "Flyweight", "Spring"],
                height: 400,
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [secondaryForceAccessor, secondaryHelixForceAccessor, secondarySpringCompForceAccessor],
        config: {
            title: "Secondary Forces vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Secondary Force", type: "value", unit: "N" },
            seriesNames: ["Net", "Helix Force", "Spring Comp Force"],
            height: 400,
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [secondaryHelixFeedbackTorqueAccessor, secondaryHelixSpringTorqueAccessor],
        config: {
            title: "Secondary Helix Torques vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Torque", type: "value", unit: "N·m" },
            seriesNames: ["Helix Feedback Torque", "Helix Spring Torque"],
            height: 400,
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [t_cAccessor, t_maxAccessor],
        config: {
            title: "Slip Model Torques vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Torque", type: "value", unit: getAxisUnit(t_cAccessor) },
            seriesNames: ["T_c", "T_max"],
            height: 400,
            showXLine: true,
            showYLine: false
        }
    },
        {
        xAccessor: engineRpmAccessor,
        yAccessor: [t_cAccessor, t_maxAccessor],
        config: {
            title: "Slip Model Torques vs Engine RPM",
            xAxis: { name: "Engine RPM", type: "value", unit: getAxisUnit(engineRpmAccessor) },
            yAxis: { name: "Torque", type: "value", unit: "N·m" },
            seriesNames: ["T_c", "T_max"],
            height: 400,
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: velocityAccessor,
        yAccessor: [totalExternalLoadAccessor, inclineForceAccessor, dragForceAccessor],
        config: {
            title: "External Load Forces vs Vehicle Speed",
            xAxis: { name: "Vehicle Speed", type: "value", unit: getAxisUnit(velocityAccessor) },
            yAxis: { name: "Force", type: "value", unit: getAxisUnit(inclineForceAccessor) },
            seriesNames: ["Total External Load", "Incline Force", "Air Resistance"],
            height: 400,
            showXLine: true,
            showYLine: false
        }
    }
];