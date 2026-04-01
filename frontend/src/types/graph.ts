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
const positionAccessor: AccessorStrategy = (point) => point.derived_state.car_position;
const velocityAccessor: AccessorStrategy = (point) => point.derived_state.car_velocity;
const accelerationAccessor: AccessorStrategy = (point) => point.drivetrain.secondary_pulley.secondary_pulley_angular_acceleration;

// Temp
const couplingTorqueAtWheels: AccessorStrategy = (point) => point.drivetrain.secondary_pulley.coupling_torque_at_secondary_pulley;
const loadTorqueAtWheels: AccessorStrategy = (point) => point.drivetrain.secondary_pulley.external_load_torque_at_secondary_pulley;

const couplingTorqueAtEngine: AccessorStrategy = (point) => point.drivetrain.primary_pulley.coupling_torque_at_primary_pulley;

// Engine and CVT stuff
const cvtRatioAccessor: AccessorStrategy = (point) => point.drivetrain.cvt_dynamics.cvt_ratio;
const engineRpmAccessor: AccessorStrategy = (point) => point.drivetrain.primary_pulley.primary_pulley_angular_velocity;
const engineTorqueAccessor: AccessorStrategy = (point) => point.drivetrain.primary_pulley.primary_pulley_drive_torque;
const cvtRatioRateOfChangeAccessor: AccessorStrategy = (point) => point.drivetrain.belt_slip.effective_cvt_ratio_time_derivative;
const enginePowerAccessor: AccessorStrategy = (point) => point.drivetrain.primary_pulley.power;
const cvtAccelerationAccessor: AccessorStrategy = (point) => point.drivetrain.cvt_dynamics.acceleration;

// Slip model accessors
const coupling_torqueAccessor: AccessorStrategy = (point) => point.drivetrain.belt_slip.coupling_torque;
const torque_demandAccessor: AccessorStrategy = (point) => point.drivetrain.belt_slip.torque_demand;
const tau_upperAccessor: AccessorStrategy = (point) => point.drivetrain.belt_slip.tau_upper;
const tau_lowerAccessor: AccessorStrategy = (point) => point.drivetrain.belt_slip.tau_lower;
const primary_tau_upperAccessor: AccessorStrategy = (point) => point.drivetrain.belt_slip.primary_tau_bounds.tau_upper;
const primary_tau_lowerAccessor: AccessorStrategy = (point) => point.drivetrain.belt_slip.primary_tau_bounds.tau_lower;
const secondary_tau_positiveAccessor: AccessorStrategy = (point) => point.drivetrain.belt_slip.secondary_tau_bounds.tau_positive;
const secondary_tau_negativeAccessor: AccessorStrategy = (point) => point.drivetrain.belt_slip.secondary_tau_bounds.tau_negative;
const relativeVelocityAccessor: AccessorStrategy = (point) => point.drivetrain.belt_state.relative_speed;
const isSlippingAccessor: AccessorStrategy = (point) => point.drivetrain.belt_slip.is_slipping ? 1 : 0;

// Belt model accessors
const primaryBeltSpeedAccessor: AccessorStrategy = (point) => point.drivetrain.belt_state.primary_belt_speed;
const secondaryBeltSpeedAccessor: AccessorStrategy = (point) => point.drivetrain.belt_state.secondary_belt_speed;
const beltSpeedAccessor: AccessorStrategy = (point) => point.drivetrain.belt_state.v_b;
const beltCompatibleSpeedAccessor: AccessorStrategy = (point) => point.drivetrain.belt_state.v_b_compatible;
const beltTargetSpeedAccessor: AccessorStrategy = (point) => point.drivetrain.belt_state.v_b_star;
const beltSpeedDerivativeAccessor: AccessorStrategy = (point) => point.drivetrain.belt_state.v_b_dot;
const beltRelaxationTimeAccessor: AccessorStrategy = (point) => point.drivetrain.belt_state.T_b;
const beltIsStickAccessor: AccessorStrategy = (point) => point.drivetrain.belt_state.is_stick ? 1 : 0;

// External load
const rollingResistanceForceAccessor: AccessorStrategy = (point) => point.drivetrain.secondary_pulley.external_forces.rolling_resistance_force;
const inclineForceAccessor: AccessorStrategy = (point) => point.drivetrain.secondary_pulley.external_forces.incline_force;
const dragForceAccessor: AccessorStrategy = (point) => point.drivetrain.secondary_pulley.external_forces.drag_force;
const totalExternalLoadForceAtCarAccessor: AccessorStrategy = (point) =>
    (point.drivetrain.secondary_pulley.external_forces as DataPoint['drivetrain']['secondary_pulley']['external_forces'] & { net_force_at_car: number }).net_force_at_car;
const rollingResistanceTorqueAtSecondaryAccessor: AccessorStrategy = (point) =>
    (point.drivetrain.secondary_pulley.external_forces as DataPoint['drivetrain']['secondary_pulley']['external_forces'] & { rolling_resistance_torque_at_secondary: number }).rolling_resistance_torque_at_secondary;
const inclineTorqueAtSecondaryAccessor: AccessorStrategy = (point) =>
    (point.drivetrain.secondary_pulley.external_forces as DataPoint['drivetrain']['secondary_pulley']['external_forces'] & { incline_torque_at_secondary: number }).incline_torque_at_secondary;
const dragTorqueAtSecondaryAccessor: AccessorStrategy = (point) =>
    (point.drivetrain.secondary_pulley.external_forces as DataPoint['drivetrain']['secondary_pulley']['external_forces'] & { drag_torque_at_secondary: number }).drag_torque_at_secondary;
const totalExternalLoadTorqueAtSecondaryAccessor: AccessorStrategy = (point) =>
    (point.drivetrain.secondary_pulley.external_forces as DataPoint['drivetrain']['secondary_pulley']['external_forces'] & { net_torque_at_secondary: number }).net_torque_at_secondary;

// Overall pulley clamping force (Axial)
const primaryAxialClampingForceAccessor: AccessorStrategy = (point) => point.drivetrain.cvt_dynamics.primaryPulleyState.forces.axial_clamping_force;
const secondaryAxialClampingForceAccessor: AccessorStrategy = (point) => point.drivetrain.cvt_dynamics.secondaryPulleyState.forces.axial_clamping_force;
const primaryAxialCentrifugalFromBeltAccessor: AccessorStrategy = (point) => point.drivetrain.cvt_dynamics.primaryPulleyState.forces.axial_centrifugal_from_belt;
const secondaryAxialCentrifugalFromBeltAccessor: AccessorStrategy = (point) => point.drivetrain.cvt_dynamics.secondaryPulleyState.forces.axial_centrifugal_from_belt;
const primaryAxialForceTotalAccessor: AccessorStrategy = (point) => point.drivetrain.cvt_dynamics.primaryPulleyState.forces.axial_force_total;
const secondaryAxialForceTotalAccessor: AccessorStrategy = (point) => point.drivetrain.cvt_dynamics.secondaryPulleyState.forces.axial_force_total;

// Helper function to extract values from breakdown with proper error handling
function getBreakdownValue<T>(
    breakdown: DataPoint['drivetrain']['cvt_dynamics']['primaryPulleyState']['breakdown'] |
               DataPoint['drivetrain']['cvt_dynamics']['secondaryPulleyState']['breakdown'],
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
    const prf = point.drivetrain.cvt_dynamics.primaryPulleyState.breakdown;
    return getBreakdownValue(prf, ['flyweightForce', 'net'], "primary pulley");
};

const rawFlyweightCentrifugalForce: AccessorStrategy = (point) => {
    const prf = point.drivetrain.cvt_dynamics.primaryPulleyState.breakdown;
    return getBreakdownValue(prf, ['flyweightForce', 'centrifugal_force'], "primary pulley");
};

const primarySpringForceAccessor: AccessorStrategy = (point) => {
    const prf = point.drivetrain.cvt_dynamics.primaryPulleyState.breakdown;
    return getBreakdownValue(prf, ['springForce', 'net'], "primary pulley");
};

const primaryRampAngleAccessor: AccessorStrategy = (point) => {
    const prf = point.drivetrain.cvt_dynamics.primaryPulleyState.breakdown;
    return getBreakdownValue(prf, ['flyweightForce', 'angle'], "primary pulley");
};

const secondaryHelixFeedbackTorqueAccessor: AccessorStrategy = (point) => {
    const srf = point.drivetrain.cvt_dynamics.secondaryPulleyState.breakdown;
    return getBreakdownValue(srf, ['helix_force', 'feedbackTorque'], "secondary pulley");
};

const secondaryHelixSpringTorqueAccessor: AccessorStrategy = (point) => {
    const srf = point.drivetrain.cvt_dynamics.secondaryPulleyState.breakdown;
    return getBreakdownValue(srf, ['helix_force', 'springTorque', 'net'], "secondary pulley");
}; 

const secondaryHelixForceAccessor: AccessorStrategy = (point) => {
    const srf = point.drivetrain.cvt_dynamics.secondaryPulleyState.breakdown;
    return getBreakdownValue(srf, ['helix_force', 'net'], "secondary pulley");
};

const secondarySpringCompForceAccessor: AccessorStrategy = (point) => {
    const srf = point.drivetrain.cvt_dynamics.secondaryPulleyState.breakdown;
    return getBreakdownValue(srf, ['springCompForce', 'net'], "secondary pulley");
}; 

// Mapping from accessor to unit type
export const accessorToUnit = new Map<AccessorStrategy, BaseUnitType>([
    [timeAccessor, 'time'],
    [positionAccessor, 'distance'],
    [velocityAccessor, 'velocity'],
    [accelerationAccessor, 'angular_acceleration'],
    [cvtRatioAccessor, 'dimensionless'],
    [engineRpmAccessor, 'angular_velocity'],
    [engineTorqueAccessor, 'torque'],
    [cvtRatioRateOfChangeAccessor, 'dimensionless_rate'],
    [enginePowerAccessor, 'power'],
    [coupling_torqueAccessor, 'torque'],
    [tau_upperAccessor, 'torque'],
    [tau_lowerAccessor, 'torque'],
    [primary_tau_upperAccessor, 'torque'],
    [primary_tau_lowerAccessor, 'torque'],
    [secondary_tau_positiveAccessor, 'torque'],
    [secondary_tau_negativeAccessor, 'torque'],
    [relativeVelocityAccessor, 'velocity'],
    [primaryBeltSpeedAccessor, 'velocity'],
    [secondaryBeltSpeedAccessor, 'velocity'],
    [beltSpeedAccessor, 'velocity'],
    [beltCompatibleSpeedAccessor, 'velocity'],
    [beltTargetSpeedAccessor, 'velocity'],
    [beltSpeedDerivativeAccessor, 'acceleration'],
    [beltRelaxationTimeAccessor, 'time'],
    [beltIsStickAccessor, 'dimensionless'],
    [torque_demandAccessor, 'torque'],
    [primaryFlyweightForceAccessor, 'force'],
    [rawFlyweightCentrifugalForce, 'force'],
    [primarySpringForceAccessor, 'force'],
    [secondaryHelixFeedbackTorqueAccessor, 'torque'],
    [secondaryHelixSpringTorqueAccessor, 'torque'],
    [secondaryHelixForceAccessor, 'force'],
    [secondarySpringCompForceAccessor, 'force'],
    [primaryAxialClampingForceAccessor, 'force'],
    [secondaryAxialClampingForceAccessor, 'force'],
    [primaryAxialCentrifugalFromBeltAccessor, 'force'],
    [secondaryAxialCentrifugalFromBeltAccessor, 'force'],
    [primaryAxialForceTotalAccessor, 'force'],
    [secondaryAxialForceTotalAccessor, 'force'],
    [rollingResistanceForceAccessor, 'force'],
    [inclineForceAccessor, 'force'],
    [dragForceAccessor, 'force'],
    [totalExternalLoadForceAtCarAccessor, 'force'],
    [rollingResistanceTorqueAtSecondaryAccessor, 'torque'],
    [inclineTorqueAtSecondaryAccessor, 'torque'],
    [dragTorqueAtSecondaryAccessor, 'torque'],
    [totalExternalLoadTorqueAtSecondaryAccessor, 'torque'],
    [isSlippingAccessor, 'dimensionless'],
    [couplingTorqueAtWheels, 'torque'],
    [loadTorqueAtWheels, 'torque'],
    [couplingTorqueAtEngine, 'torque'],
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
                seriesNames: ["Coupling Torque at Secondary", "Load Torque at Secondary"],
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
        }
    ]
},
{
    title: "External Load",
    graphs: [
    /** EXTERNAL LOAD */
    {
        xAccessor: velocityAccessor,
        yAccessor: [totalExternalLoadForceAtCarAccessor, rollingResistanceForceAccessor, inclineForceAccessor, dragForceAccessor],
        config: {
            title: "External Load Forces at Car vs Vehicle Speed",
            xAxis: { name: "Vehicle Speed", type: "value", unit: getAxisUnit(velocityAccessor) },
            yAxis: { name: "Force", type: "value", unit: getAxisUnit(inclineForceAccessor) },
            seriesNames: ["Total (Car)", "Rolling Resistance", "Incline Force", "Air Resistance"],
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: velocityAccessor,
        yAccessor: [totalExternalLoadTorqueAtSecondaryAccessor, rollingResistanceTorqueAtSecondaryAccessor, inclineTorqueAtSecondaryAccessor, dragTorqueAtSecondaryAccessor],
        config: {
            title: "External Load Torques at Secondary vs Vehicle Speed",
            xAxis: { name: "Vehicle Speed", type: "value", unit: getAxisUnit(velocityAccessor) },
            yAxis: { name: "Torque", type: "value", unit: getAxisUnit(totalExternalLoadTorqueAtSecondaryAccessor) },
            seriesNames: ["Total (Secondary)", "Rolling Resistance", "Incline Torque", "Air Resistance Torque"],
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
    {
        xAccessor: engineRpmAccessor,
        yAccessor: [engineTorqueAccessor, primary_tau_upperAccessor],
        config: {
            title: "Engine Torque and Primary Upper Bound vs Engine RPM",
            xAxis: { name: "Engine RPM", type: "value", unit: getAxisUnit(engineRpmAccessor) },
            yAxis: { name: "Torque", type: "value", unit: getAxisUnit(engineTorqueAccessor) },
            seriesNames: ["Engine Torque", "Primary Upper Bound"],
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
        yAccessor: [primaryAxialForceTotalAccessor, secondaryAxialForceTotalAccessor],
        config: {
            title: "Pulley Total Axial Forces vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Axial Force", type: "value", unit: "N" },
            seriesNames: ["Primary Total", "Secondary Total"],
            showXLine: true,
            showYLine: false
        }
    },
    { // Breakdown of axial clamping and belt centrifugal contribution
        xAccessor: timeAccessor,
        yAccessor: [primaryAxialClampingForceAccessor, secondaryAxialClampingForceAccessor, primaryAxialCentrifugalFromBeltAccessor, secondaryAxialCentrifugalFromBeltAccessor],
        config: {
            title: "Axial Force Breakdown vs Time",
            xAxis: { name: "Time", type: "value", unit: "s" },
            yAxis: { name: "Force", type: "value", unit: "N" },
            seriesNames: ["Primary Clamping", "Secondary Clamping", "Primary Belt Centrifugal", "Secondary Belt Centrifugal"],
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
        yAccessor: [primaryAxialClampingForceAccessor, primaryFlyweightForceAccessor, primarySpringForceAccessor],
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
        yAccessor: [secondaryAxialClampingForceAccessor, secondaryHelixForceAccessor, secondarySpringCompForceAccessor],
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
        yAccessor: [secondaryAxialClampingForceAccessor, secondaryHelixForceAccessor, secondarySpringCompForceAccessor],
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
    { // Per-pulley torque bounds
        xAccessor: timeAccessor,
        yAccessor: [
            primary_tau_upperAccessor,
            primary_tau_lowerAccessor,
            secondary_tau_positiveAccessor,
            secondary_tau_negativeAccessor
        ],
        config: {
            title: "Primary and Secondary Torque Bounds vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Torque", type: "value", unit: getAxisUnit(coupling_torqueAccessor) },
            seriesNames: [
                "Primary Upper Bound",
                "Primary Lower Bound",
                "Secondary Upper Bound",
                "Secondary Lower Bound"
            ],
            showXLine: true,
            showYLine: false
        }
    },
    { // Overall bounds and torque tracking
        xAccessor: timeAccessor,
        yAccessor: [tau_upperAccessor, tau_lowerAccessor, coupling_torqueAccessor, torque_demandAccessor],
        config: {
            title: "Overall Bounds, Coupling, and No-Slip Torque vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Torque", type: "value", unit: "N·m" },
            seriesNames: ["Overall Upper Bound", "Overall Lower Bound", "Coupling (Final)", "No-Slip Torque"],
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [relativeVelocityAccessor],
        config: {
            title: "Relative Velocity vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Relative Velocity", type: "value", unit: getAxisUnit(relativeVelocityAccessor) },
            showXLine: true,
            showYLine: false
        }
    }
]},
{
    title: "Belt Debug",
    graphs: [
    {
        xAccessor: timeAccessor,
        yAccessor: [primaryBeltSpeedAccessor, secondaryBeltSpeedAccessor, beltSpeedAccessor, beltTargetSpeedAccessor],
        config: {
            title: "Belt Speeds vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Speed", type: "value", unit: getAxisUnit(beltSpeedAccessor) },
            seriesNames: ["Primary Belt Speed", "Secondary Belt Speed", "Transport Speed v_b", "Target Speed v_b*"],
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [relativeVelocityAccessor, beltCompatibleSpeedAccessor, beltSpeedDerivativeAccessor],
        config: {
            title: "Belt Relative Speed and Dynamics vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Belt Diagnostics", type: "value", unit: getAxisUnit(relativeVelocityAccessor) },
            seriesNames: ["Relative Speed (v_p - v_s)", "Compatible Speed", "v_b_dot"],
            showXLine: true,
            showYLine: false
        }
    },
    {
        xAccessor: timeAccessor,
        yAccessor: [beltIsStickAccessor, isSlippingAccessor, beltRelaxationTimeAccessor],
        config: {
            title: "Belt Mode Flags and Relaxation Time vs Time",
            xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
            yAxis: { name: "Mode / Time Constant", type: "value", unit: getAxisUnit(beltRelaxationTimeAccessor) },
            seriesNames: ["is_stick (belt)", "is_slipping (slip model)", "T_b"],
            showXLine: true,
            showYLine: false
        }
    }
]}
];

// Flatten categories into single array for backward compatibility
export const graphConfigs: GraphConfig[] = graphCategories.flatMap(category => category.graphs);