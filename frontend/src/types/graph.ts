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

export type GraphCategory = {
    title: string;
    graphs: GraphConfig[];
};

export const timeAccessor: AccessorStrategy = (point) => point.time;
const positionAccessor: AccessorStrategy = (point) => point.state.car_position;
const velocityAccessor: AccessorStrategy = (point) => point.state.car_velocity;
const accelerationAccessor: AccessorStrategy = (point) => point.system.car.acceleration;

// Temp
const couplingTorqueAtWheels: AccessorStrategy = (point) => point.system.car.coupling_torque_at_wheel;
const loadTorqueAtWheels: AccessorStrategy = (point) => point.system.car.load_torque_at_wheel;
const powerAtWheelAccessor: AccessorStrategy = (point) => point.system.car.power_at_wheel;

const couplingTorqueAtEngine: AccessorStrategy = (point) => point.system.engine.coupling_torque_at_engine;

// Engine and CVT stuff
const cvtRatioAccessor: AccessorStrategy = (point) => point.system.cvt.cvt_ratio;
const engineRpmAccessor: AccessorStrategy = (point) => point.system.engine.angular_velocity;
const engineTorqueAccessor: AccessorStrategy = (point) => point.system.engine.torque;
const cvtRatioRateOfChangeAccessor: AccessorStrategy = (point) => point.system.slip.cvt_ratio_derivative;
const enginePowerAccessor: AccessorStrategy = (point) => point.system.engine.power;
const cvtAccelerationAccessor: AccessorStrategy = (point) => point.system.cvt.acceleration;

// Slip model accessors
const t_max_primAccessor: AccessorStrategy = (point) => point.system.slip.t_max_prim;
const t_max_secAccessor: AccessorStrategy = (point) => point.system.slip.t_max_sec;
const coupling_torqueAccessor: AccessorStrategy = (point) => point.system.slip.coupling_torque;
const torque_demandAccessor: AccessorStrategy = (point) => point.system.slip.torque_demand;
const isSlippingAccessor: AccessorStrategy = (point) => point.system.slip.is_slipping ? 1 : 0;

// External load
const inclineForceAccessor: AccessorStrategy = (point) => point.system.car.external_forces.incline_force;
const dragForceAccessor: AccessorStrategy = (point) => point.system.car.external_forces.drag_force;
const totalExternalLoadAccessor: AccessorStrategy = (point) => point.system.car.external_forces.net;

// Overall pulley radial force (combined)
const primaryRadialForceAccessor: AccessorStrategy = (point) => point.system.cvt.primaryPulleyState.forces.radial_force;
const secondaryRadialForceAccessor: AccessorStrategy = (point) => point.system.cvt.secondaryPulleyState.forces.radial_force;

// Components of radial force prior to 2sin(phi/2) multiplication
const primaryRadialFromCentrifugalAccessor: AccessorStrategy = (point) => point.system.cvt.primaryPulleyState.radial_from_centrifugal;
const primaryRadialFromClampingAccessor: AccessorStrategy = (point) => point.system.cvt.primaryPulleyState.radial_from_clamping;
const secondaryRadialFromCentrifugalAccessor: AccessorStrategy = (point) => point.system.cvt.secondaryPulleyState.radial_from_centrifugal;
const secondaryRadialFromClampingAccessor: AccessorStrategy = (point) => point.system.cvt.secondaryPulleyState.radial_from_clamping;

// Overall pulley clamping force (Axial)
const primaryClampingForceAccessor: AccessorStrategy = (point) => point.system.cvt.primaryPulleyState.forces.clamping_force;
const secondaryClampingForceAccessor: AccessorStrategy = (point) => point.system.cvt.secondaryPulleyState.forces.clamping_force;

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

const rawFlyweightCentrifugalForce: AccessorStrategy = (point) => {
    const prf = point.system.cvt.primaryPulleyState.breakdown;
    return getBreakdownValue(prf, ['flyweightForce', 'centrifugal_force'], "primary pulley");
};

const primarySpringForceAccessor: AccessorStrategy = (point) => {
    const prf = point.system.cvt.primaryPulleyState.breakdown;
    return getBreakdownValue(prf, ['springForce', 'net'], "primary pulley");
};

const primaryRampAngleAccessor: AccessorStrategy = (point) => {
    const prf = point.system.cvt.primaryPulleyState.breakdown;
    return getBreakdownValue(prf, ['flyweightForce', 'angle'], "primary pulley");
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
    [coupling_torqueAccessor, 'torque'],
    [t_max_primAccessor, 'torque'],
    [t_max_secAccessor, 'torque'],
    [torque_demandAccessor, 'torque'],
    [primaryRadialForceAccessor, 'force'],
    [secondaryRadialForceAccessor, 'force'],
    [primaryFlyweightForceAccessor, 'force'],
    [rawFlyweightCentrifugalForce, 'force'],
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
    [primaryRadialFromCentrifugalAccessor, 'force'],
    [primaryRadialFromClampingAccessor, 'force'],
    [secondaryRadialFromCentrifugalAccessor, 'force'],
    [secondaryRadialFromClampingAccessor, 'force'],
    [isSlippingAccessor, 'dimensionless'],
    [couplingTorqueAtWheels, 'torque'],
    [loadTorqueAtWheels, 'torque'],
    [couplingTorqueAtEngine, 'torque'],
    [powerAtWheelAccessor, 'power'],
]);

// Helper function to get unit label for an accessor
function getAxisUnit(accessor: AccessorStrategy): string {
    const unitType = accessorToUnit.get(accessor);
    if (!unitType) return 'No unit associated with accessor!';
    
    // Get BAJA unit as default
    const unit = getTargetUnit(unitType, UNIT_PRESETS.BAJA);
    return unit || '';
}

export const graphCategories: GraphCategory[] = [
    {
        title: "Kinematics",
        graphs: [
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
]},
{
    title: "Acceleration of Engine and Car",
    graphs: [
        // Graphs for looking at accelration of engine and wheels as separate systems
        {
            xAccessor: timeAccessor,
            yAccessor: [couplingTorqueAtWheels, loadTorqueAtWheels],
            config: {
                title: "Torques at Wheels vs Time",
                xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                yAxis: { name: "Torque", type: "value", unit: getAxisUnit(couplingTorqueAtWheels) },
                seriesNames: ["Coupling Torque at Wheels", "Load Torque at Wheels"],
                showXLine: true,
                showYLine: false
            }
        },
        {
            xAccessor: timeAccessor,
            yAccessor: [couplingTorqueAtEngine, engineTorqueAccessor],
            config: {
                title: "Torques at Engine vs Time",
                xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                yAxis: { name: "Torque", type: "value", unit: getAxisUnit(couplingTorqueAtEngine) },
                seriesNames: ["Coupling Torque at Engine", "Engine Torque"],
                showXLine: true,
                showYLine: false
            }
        },
        {
            xAccessor: timeAccessor,
            yAccessor: [powerAtWheelAccessor],
            config: {
                title: "Power at Wheels vs Time",
                xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                yAxis: { name: "Power", type: "value", unit: getAxisUnit(powerAtWheelAccessor) },
                showXLine: true,
                showYLine: false
            }
        }
    ]
},
{
    title: "External Load",
    graphs: [
    /** EXTERNAL LOAD */
    {
        xAccessor: velocityAccessor,
        yAccessor: [totalExternalLoadAccessor, inclineForceAccessor, dragForceAccessor],
        config: {
            title: "External Load Forces vs Vehicle Speed",
            xAxis: { name: "Vehicle Speed", type: "value", unit: getAxisUnit(velocityAccessor) },
            yAxis: { name: "Force", type: "value", unit: getAxisUnit(inclineForceAccessor) },
            seriesNames: ["Total External Load", "Incline Force", "Air Resistance"],
            showXLine: true,
            showYLine: false
        }
    },
]},
{
    title: "CVT Ratio",
    graphs: [
    /** CVT RATIO GRAPHS */
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
]},
{
    title: "Engine",
    graphs: [
    /** ENGINE GRAPHS */
    {
        xAccessor: timeAccessor,
        yAccessor: [engineRpmAccessor],
        config: {
            title: "Engine RPM vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Engine RPM", type: "value", unit: getAxisUnit(engineRpmAccessor) },
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
]},
{
    title: "Pulley Forces (Overall)",
    graphs: [
    /** PRIM AND SEC OVERALL GRAPHS */
    { // Shows overall direction of shift
        xAccessor: timeAccessor,
        yAccessor: [primaryRadialForceAccessor, secondaryRadialForceAccessor],
        config: {
            title: "Pulley Net Radial Forces vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Radial Force", type: "value", unit: "N" },
            seriesNames: ["Primary Net", "Secondary Net"],
            showXLine: true,
            showYLine: false
        }
    },
    { // Breakdown of radial force in belt centrifugal and clamping
        xAccessor: timeAccessor,
        yAccessor: [ primaryRadialFromClampingAccessor, secondaryRadialFromClampingAccessor, primaryRadialFromCentrifugalAccessor, secondaryRadialFromCentrifugalAccessor],
        config: {
            title: "Radial Breakdown vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Force", type: "value", unit: "N" },
            seriesNames: ["Primary Pulley", "Secondary Pulley", "Primary Centrifugal", "Secondary Centrifugal"],
            showXLine: true,
            showYLine: false
        }
    },
    // cvtAccelerationAccessor
    {
        xAccessor: timeAccessor,
        yAccessor: [cvtAccelerationAccessor],
        config: {
            title: "CVT Acceleration vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "CVT Acceleration", type: "value", unit: getAxisUnit(cvtAccelerationAccessor) },
            showXLine: true,
            showYLine: false
        }
    },
]},
{
    title: "Primary Pulley",
    graphs: [
    /** PRIMARY GRAPHS */
    { // Primary axial force breakdown into components
        xAccessor: timeAccessor,
        yAccessor: [primaryClampingForceAccessor, primaryFlyweightForceAccessor, primarySpringForceAccessor],
        config: {
            title: "Primary Axial Forces vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Force", type: "value", unit: "N" },
            seriesNames: ["Net", "Flyweight", "Spring"],
            showXLine: true,
            showYLine: false
        }
    },
    { // Visualize how much ramp is doing(raw vs post ramp)
        xAccessor: engineRpmAccessor,
        yAccessor: [rawFlyweightCentrifugalForce, primaryFlyweightForceAccessor],
        config: {
            title: "Ramp Impact (Raw vs Post-Ramp) vs Engine RPM",
            xAxis: { name: "Engine RPM", type: "value", unit: getAxisUnit(engineRpmAccessor) },
            yAxis: { name: "Force", type: "value", unit: "N" },
            seriesNames: ["Raw Flyweight", "Flyweight"],
            showXLine: true,
            showYLine: true
        }
    },
    // primaryRampAngleAccessor
    {
        xAccessor: timeAccessor,
        yAccessor: [primaryRampAngleAccessor],
        config: {
            title: "Primary Ramp Angle vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Ramp Angle", type: "value", unit: "degrees" },
            showXLine: true,
            showYLine: false
        }
    },
]},
{
    title: "Secondary Pulley",
    graphs: [
    /** SECONDARY GRAPHS */
    { // Top level breakdown of axial from helix and axial from spring
        xAccessor: timeAccessor,
        yAccessor: [secondaryClampingForceAccessor, secondaryHelixForceAccessor, secondarySpringCompForceAccessor],
        config: {
            title: "Secondary Axial Forces vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Secondary Force", type: "value", unit: "N" },
            seriesNames: ["Net", "Helix Force", "Spring Comp Force"],
            showXLine: true,
            showYLine: false
        }
    },
    { // Torques that go into the helix
        xAccessor: timeAccessor,
        yAccessor: [secondaryHelixFeedbackTorqueAccessor, secondaryHelixSpringTorqueAccessor],
        config: {
            title: "Secondary Torques vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Torque", type: "value", unit: "N·m" },
            seriesNames: ["Reactive Feedback", "Torsional Spring"],
            showXLine: true,
            showYLine: false
        }
    },
    { // Same graph as 2 above, but vs CVT ratio
        xAccessor: cvtRatioAccessor,
        yAccessor: [secondaryClampingForceAccessor, secondaryHelixForceAccessor, secondarySpringCompForceAccessor],
        config: {
            title: "Secondary Axial Forces vs CVT RATIO",
            xAxis: { name: "CVT RATIO", type: "value", unit: getAxisUnit(cvtRatioAccessor) },
            yAxis: { name: "Secondary Force", type: "value", unit: "N" },
            seriesNames: ["Net", "Helix Force", "Spring Comp Force"],
            showXLine: true,
            showYLine: false
        }
    },
    { // Same graph as 2 above, but vs CVT ratio
        xAccessor: cvtRatioAccessor,
        yAccessor: [secondaryHelixFeedbackTorqueAccessor, secondaryHelixSpringTorqueAccessor],
        config: {
            title: "Secondary Torques vs CVT RATIO",
            xAxis: { name: "CVT RATIO", type: "value", unit: getAxisUnit(cvtRatioAccessor) },
            yAxis: { name: "Torque", type: "value", unit: "N·m" },
            seriesNames: ["Reactive Feedback", "Torsional Spring"],
            showXLine: true,
            showYLine: false
        }
    },
]},
{
    title: "Slip Model",
    graphs: [
    /** SLIP MODEL GRAPHS */
    { // Slip model torques vs time
        xAccessor: timeAccessor,
        yAccessor: [coupling_torqueAccessor, torque_demandAccessor, t_max_primAccessor, t_max_secAccessor],
        config: {
            title: "Slip Model Torques vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Torque", type: "value", unit: getAxisUnit(coupling_torqueAccessor) },
            seriesNames: ["Coupling", "Demand", "T_max (Primary)", "T_max (Secondary)"],
            showXLine: true,
            showYLine: false
        }
    },
    { // Same graph but vs Engine RPM (is this useful?)
        xAccessor: engineRpmAccessor,
        yAccessor: [coupling_torqueAccessor, t_max_primAccessor, t_max_secAccessor],
        config: {
            title: "Slip Model Torques vs Engine RPM",
            xAxis: { name: "Engine RPM", type: "value", unit: getAxisUnit(engineRpmAccessor) },
            yAxis: { name: "Torque", type: "value", unit: "N·m" },
            seriesNames: ["Coupling", "T_max (Primary)", "T_max (Secondary)"],
            showXLine: true,
            showYLine: false
        }
    },
    { // Whether you are slipping or not vs time
        xAccessor: timeAccessor,
        yAccessor: [isSlippingAccessor],
        config: {
            title: "Is Slipping vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Is Slipping", type: "value", unit: "dimensionless" },
            showXLine: true,
            showYLine: false
        }
    }
]}
];

// Flatten categories into single array for backward compatibility
export const graphConfigs: GraphConfig[] = graphCategories.flatMap(category => category.graphs);