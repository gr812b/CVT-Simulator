import type { ChartConfig } from "@components/graph2D/chartOptions";
import type { RunResponse } from "@utils/api";
import type { BaseUnitType } from "@utils/conversion";
import { UNIT_PRESETS, getTargetUnit } from "@utils/conversion";

type DataPoint = RunResponse['data'][number]; // TODO: Move to somewhere else (maybe replay controller file)

type AccessorStrategy = (point: DataPoint) => number;

type GraphConfig = {
    xAccessor: AccessorStrategy;
    yAccessor: AccessorStrategy[];
    config: ChartConfig;
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
const t_max_primAccessor: AccessorStrategy = (point) => point.system.slip.t_max_prim;
const t_max_secAccessor: AccessorStrategy = (point) => point.system.slip.t_max_sec;
const t_cAccessor: AccessorStrategy = (point) => point.system.slip.t_c;
const t_c_before_clampAccessor: AccessorStrategy = (point) => point.system.slip.t_c_before_clamp;
const primaryRadialForceAccessor: AccessorStrategy = (point) => point.system.cvt.primaryPulleyState.forces.radial_force;
const primaryClampingForceAccessor: AccessorStrategy = (point) => point.system.cvt.primaryPulleyState.forces.clamping_force;
const secondaryRadialForceAccessor: AccessorStrategy = (point) => point.system.cvt.secondaryPulleyState.forces.radial_force;
const secondaryClampingForceAccessor: AccessorStrategy = (point) => point.system.cvt.secondaryPulleyState.forces.clamping_force;
const inclineForceAccessor: AccessorStrategy = (point) => point.system.car.external_forces.incline_force;
const dragForceAccessor: AccessorStrategy = (point) => point.system.car.external_forces.drag_force;
const totalExternalLoadAccessor: AccessorStrategy = (point) => point.system.car.external_forces.net;
const primaryCentrifugalForceAccessor: AccessorStrategy = (point) => point.system.cvt.primaryPulleyState.radial_from_centrifugal;
const primaryRadialFromClampingAccessor: AccessorStrategy = (point) => point.system.cvt.primaryPulleyState.radial_from_clamping;
const secondaryCentrifugalForceAccessor: AccessorStrategy = (point) => point.system.cvt.secondaryPulleyState.radial_from_centrifugal;
const secondaryRadialFromClampingAccessor: AccessorStrategy = (point) => point.system.cvt.secondaryPulleyState.radial_from_clamping;
const isSlippingAccessor: AccessorStrategy = (point) => point.system.slip.is_slipping ? 1 : 0;

// Helper function to extract values from breakdown with proper error handling
function getBreakdownValue<T>(
    breakdown: DataPoint['system']['cvt']['primaryPulleyState']['breakdown'] | 
               DataPoint['system']['cvt']['secondaryPulleyState']['breakdown'], 
    propertyPath: string[], 
    contextName: string = "breakdown"
): T {
    let current: unknown = breakdown;
    
    for (const prop of propertyPath) {
        if (typeof current !== 'object' || current === null || !(prop in current)) {
            throw new Error(`Missing property '${prop}' in ${contextName} breakdown. Expected path: ${propertyPath.join('.')}. This indicates a data structure mismatch.`);
        }
        
        current = (current as Record<string, unknown>)[prop];
        
        if (current == null) {
            throw new Error(`Property '${prop}' is null/undefined in ${contextName} breakdown. Expected path: ${propertyPath.join('.')}. This indicates a data structure mismatch.`);
        }
    }
    
    return current as T;
}

const primaryFlyweightForceAccessor: AccessorStrategy = (point) => {
    const prf = point.system.cvt.primaryPulleyState.breakdown;
    return getBreakdownValue(prf, ['flyweightForce', 'net'], "primary pulley");
};

const primarySpringForceAccessor: AccessorStrategy = (point) => {
    const prf = point.system.cvt.primaryPulleyState.breakdown;
    return getBreakdownValue(prf, ['springForce', 'net'], "primary pulley");
};

const secondaryHelixFeedbackTorqueAccessor: AccessorStrategy = (point) => {
    const srf = point.system.cvt.secondaryPulleyState.breakdown;
    return getBreakdownValue(srf, ['helix_force', 'feedbackTorque'], "secondary pulley");
};

const secondaryHelixSpringTorqueAccessor: AccessorStrategy = (point) => {
    const srf = point.system.cvt.secondaryPulleyState.breakdown;
    return getBreakdownValue(srf, ['helix_force', 'springTorque', 'net'], "secondary pulley");
}; 

const secondaryHelixForceAccessor: AccessorStrategy = (point) => {
    const srf = point.system.cvt.secondaryPulleyState.breakdown;
    return getBreakdownValue(srf, ['helix_force', 'net'], "secondary pulley");
};

const secondarySpringCompForceAccessor: AccessorStrategy = (point) => {
    const srf = point.system.cvt.secondaryPulleyState.breakdown;
    return getBreakdownValue(srf, ['springCompForce', 'net'], "secondary pulley");
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
    [cvtRatioRateOfChangeAccessor, 'dimensionless_rate'],
    [enginePowerAccessor, 'power'],
    [t_cAccessor, 'torque'],
    [t_max_primAccessor, 'torque'],
    [t_max_secAccessor, 'torque'],
    [t_c_before_clampAccessor, 'torque'],
    [primaryRadialForceAccessor, 'force'],
    [secondaryRadialForceAccessor, 'force'],
    [primaryFlyweightForceAccessor, 'force'],
    [primarySpringForceAccessor, 'force'],
    [secondaryHelixFeedbackTorqueAccessor, 'torque'],
    [secondaryHelixSpringTorqueAccessor, 'torque'],
    [secondaryHelixForceAccessor, 'force'],
    [secondarySpringCompForceAccessor, 'force'],
    [primaryClampingForceAccessor, 'force'],
    [secondaryClampingForceAccessor, 'force'],
    [inclineForceAccessor, 'force'],
    [dragForceAccessor, 'force'],
    [totalExternalLoadAccessor, 'force'],
    [primaryCentrifugalForceAccessor, 'force'],
    [primaryRadialFromClampingAccessor, 'force'],
    [secondaryCentrifugalForceAccessor, 'force'],
    [secondaryRadialFromClampingAccessor, 'force'],
    [isSlippingAccessor, 'dimensionless'],
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
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [primaryCentrifugalForceAccessor, primaryRadialFromClampingAccessor, secondaryCentrifugalForceAccessor, secondaryRadialFromClampingAccessor],
        config: {
            title: "Pulley Force Components vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Force", type: "value", unit: "N" },
            seriesNames: ["Primary Centrifugal", "Primary Pulley", "Secondary Centrifugal", "Secondary Pulley"],
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
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [primaryClampingForceAccessor, primaryFlyweightForceAccessor, primarySpringForceAccessor],
        config: {
            title: "Primary Forces vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Primary Force", type: "value", unit: "N" },
            seriesNames: ["Net", "Flyweight", "Spring"],
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
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [secondaryClampingForceAccessor, secondaryHelixForceAccessor, secondarySpringCompForceAccessor],
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
        yAccessor: [t_cAccessor, t_max_primAccessor, t_max_secAccessor],
        config: {
            title: "Slip Model Torques vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Torque", type: "value", unit: getAxisUnit(t_cAccessor) },
            seriesNames: ["T_c", "T_c (Before Clamp)", "T_max (Primary)", "T_max (Secondary)"],
            height: 400,
            showXLine: true,
            showYLine: false
        }
    },
        {
        xAccessor: engineRpmAccessor,
        yAccessor: [t_cAccessor, t_max_primAccessor, t_max_secAccessor],
        config: {
            title: "Slip Model Torques vs Engine RPM",
            xAxis: { name: "Engine RPM", type: "value", unit: getAxisUnit(engineRpmAccessor) },
            yAxis: { name: "Torque", type: "value", unit: "N·m" },
            seriesNames: ["T_c", "T_max (Primary)", "T_max (Secondary)"],
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
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [isSlippingAccessor],
        config: {
            title: "Is Slipping vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Is Slipping", type: "value", unit: "dimensionless" },
            height: 400,
            showXLine: true,
            showYLine: false
        }
    }
];