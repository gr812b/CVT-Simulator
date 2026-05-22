import { TooltipPosition, type ChartConfig } from "@components/graph2D/chartOptions";
import type { RunResponse } from "@utils/api";
import type { BaseUnitType } from "@utils/conversion";
import { UNIT_PRESETS, getTargetUnit } from "@utils/conversion";

type DataPoint = RunResponse['data'][number];

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

// Basic accessors
export const timeAccessor: AccessorStrategy = (point) => point.time;
const positionAccessor: AccessorStrategy = (point) => point.derived_state.car_position;
const velocityAccessor: AccessorStrategy = (point) => point.derived_state.car_velocity;
const accelerationAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.ω_s_dot;

// Torques / coupling
const couplingTorqueAtWheels: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.tau_s;
const loadTorqueAtWheels: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.external_load_breakdown.net_torque_at_secondary;
const couplingTorqueAtEngine: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.tau_p;

// Engine and CVT stuff
const cvtRatioAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.effective_cvt_ratio;
const cvtRatioRateOfChangeAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.effective_cvt_ratio_rate_of_change;
const primaryGeometryRateAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.primary_outer_radius_rate_of_change;
const secondaryGeometryRateAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.secondary_outer_radius_rate_of_change;
const engineRpmAccessor: AccessorStrategy = (point) => point.derived_state.engine_angular_velocity;
const engineTorqueAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.engine_breakdown.engine_torque;
const enginePowerAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.engine_breakdown.engine_power;
const cvtAccelerationAccessor: AccessorStrategy = (point) => point.contact_breakdown.shift.acceleration;

// Slip model accessors
const coupling_torqueAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.tau_p;
const torque_demandAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.no_slip.tau_p_ns;
const tau_upperAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.admissibility.primary_tau_p_stick_upper;
const tau_lowerAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.admissibility.primary_tau_p_stick_lower;
const primary_tau_upperAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.admissibility.primary_tau_p_stick_upper;
const primary_tau_lowerAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.admissibility.primary_tau_p_stick_lower;
const secondary_tau_positiveAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.admissibility.secondary_tau_stick_upper;
const secondary_tau_negativeAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.admissibility.secondary_tau_stick_lower;
const relativeVelocityAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.primary_relative_speed - point.contact_breakdown.contact.slip_metrics.secondary_relative_speed;
const isSlippingAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.branch === 'NO_SLIP' ? 0 : 1;

// External load
const rollingResistanceForceAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.external_load_breakdown.rolling_resistance_force;
const inclineForceAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.external_load_breakdown.incline_force;
const dragForceAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.external_load_breakdown.drag_force;
const totalExternalLoadForceAtCarAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.external_load_breakdown.net_force_at_car;
const rollingResistanceTorqueAtSecondaryAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.external_load_breakdown.rolling_resistance_torque_at_secondary;
const inclineTorqueAtSecondaryAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.external_load_breakdown.incline_torque_at_secondary;
const dragTorqueAtSecondaryAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.external_load_breakdown.drag_torque_at_secondary;
const totalExternalLoadTorqueAtSecondaryAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.external_load_breakdown.net_torque_at_secondary;

// Pulley / axial forces
const primaryAxialClampingForceAccessor: AccessorStrategy = (point) => point.contact_breakdown.shift.primaryPulleyState.pulley_breakdown.net;
const secondaryAxialClampingForceAccessor: AccessorStrategy = (point) => point.contact_breakdown.shift.secondaryPulleyState.pulley_breakdown.net;
const primaryAxialCentrifugalFromBeltAccessor: AccessorStrategy = (point) => point.contact_breakdown.shift.primaryPulleyState.belt_wrap.axial_belt_force;
const secondaryAxialCentrifugalFromBeltAccessor: AccessorStrategy = (point) => point.contact_breakdown.shift.secondaryPulleyState.belt_wrap.axial_belt_force;
const primaryAxialForceTotalAccessor: AccessorStrategy = (point) => point.contact_breakdown.shift.primaryPulleyState.net;
const secondaryAxialForceTotalAccessor: AccessorStrategy = (point) => point.contact_breakdown.shift.secondaryPulleyState.net;

// Pulley breakdown helpers
function getBreakdownValue<T>(
    breakdown: DataPoint['contact_breakdown']['shift']['primaryPulleyState']['pulley_breakdown'] |
               DataPoint['contact_breakdown']['shift']['secondaryPulleyState']['pulley_breakdown'],
    propertyPath: string[],
    contextName: string = "breakdown"
): T {
    let current: unknown = breakdown;
    for (const prop of propertyPath) {
        if (typeof current !== 'object' || current === null || !(prop in (current as Record<string, unknown>))) {
            throw new Error(`Missing property '${prop}' in ${contextName} breakdown. Expected path: ${propertyPath.join('.')}.`);
        }
        current = (current as Record<string, unknown>)[prop];
        if (current == null) throw new Error(`Property '${prop}' is null/undefined in ${contextName} breakdown.`);
    }
    return current as T;
}

const primaryFlyweightForceAccessor: AccessorStrategy = (point) => {
    const prf = point.contact_breakdown.shift.primaryPulleyState.pulley_breakdown;
    return getBreakdownValue(prf, ['flyweightForce', 'net'], "primary pulley");
};
const rawFlyweightCentrifugalForce: AccessorStrategy = (point) => {
    const prf = point.contact_breakdown.shift.primaryPulleyState.pulley_breakdown;
    return getBreakdownValue(prf, ['flyweightForce', 'centrifugal_force'], "primary pulley");
};
const primarySpringForceAccessor: AccessorStrategy = (point) => {
    const prf = point.contact_breakdown.shift.primaryPulleyState.pulley_breakdown;
    return getBreakdownValue(prf, ['springForce', 'net'], "primary pulley");
};
const primaryRampAngleAccessor: AccessorStrategy = (point) => {
    const prf = point.contact_breakdown.shift.primaryPulleyState.pulley_breakdown;
    return getBreakdownValue(prf, ['flyweightForce', 'angle'], "primary pulley");
};

const secondaryHelixFeedbackTorqueAccessor: AccessorStrategy = (point) => {
    const srf = point.contact_breakdown.shift.secondaryPulleyState.pulley_breakdown;
    return getBreakdownValue(srf, ['helix_force', 'feedbackTorque'], "secondary pulley");
};
const secondaryHelixSpringTorqueAccessor: AccessorStrategy = (point) => {
    const srf = point.contact_breakdown.shift.secondaryPulleyState.pulley_breakdown;
    return getBreakdownValue(srf, ['helix_force', 'springTorque', 'net'], "secondary pulley");
};
const secondaryHelixForceAccessor: AccessorStrategy = (point) => {
    const srf = point.contact_breakdown.shift.secondaryPulleyState.pulley_breakdown;
    return getBreakdownValue(srf, ['helix_force', 'net'], "secondary pulley");
};
const secondarySpringCompForceAccessor: AccessorStrategy = (point) => {
    const srf = point.contact_breakdown.shift.secondaryPulleyState.pulley_breakdown;
    return getBreakdownValue(srf, ['springCompForce', 'net'], "secondary pulley");
};

// Mapping from accessor to unit type (belt-state entries intentionally omitted)
export const accessorToUnit = new Map<AccessorStrategy, BaseUnitType>([
    [timeAccessor, 'time'],
    [positionAccessor, 'distance'],
    [velocityAccessor, 'velocity'],
    [accelerationAccessor, 'angular_acceleration'],
    [cvtRatioAccessor, 'dimensionless'],
    [cvtRatioRateOfChangeAccessor, 'dimensionless_rate'],
    [primaryGeometryRateAccessor, 'velocity'],
    [secondaryGeometryRateAccessor, 'velocity'],
    [engineRpmAccessor, 'angular_velocity'],
    [engineTorqueAccessor, 'torque'],
    [enginePowerAccessor, 'power'],
    [coupling_torqueAccessor, 'torque'],
    [tau_upperAccessor, 'torque'],
    [tau_lowerAccessor, 'torque'],
    [primary_tau_upperAccessor, 'torque'],
    [primary_tau_lowerAccessor, 'torque'],
    [secondary_tau_positiveAccessor, 'torque'],
    [secondary_tau_negativeAccessor, 'torque'],
    [relativeVelocityAccessor, 'velocity'],
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

// Helper to get axis unit label
function getAxisUnit(accessor: AccessorStrategy): string {
    const unitType = accessorToUnit.get(accessor);
    if (!unitType) return '';
    const unit = getTargetUnit(unitType, UNIT_PRESETS.BAJA);
    return unit || '';
}

// Graph categories (belt debug removed)
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
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopLeft,
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
                    showYLine: true,
                    tooltipPosition: TooltipPosition.BottomRight,
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
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopRight,
                }
            }
        ]
    },
    {
        title: "Acceleration of Engine and Car",
        graphs: [
            {
                xAccessor: timeAccessor,
                yAccessor: [couplingTorqueAtWheels, loadTorqueAtWheels],
                config: {
                    title: "Torques at Wheels vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Torque", type: "value", unit: getAxisUnit(couplingTorqueAtWheels) },
                    seriesNames: ["Coupling Torque at Secondary", "Load Torque at Secondary"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopRight,
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
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopRight,
                }
            }
        ]
    },
    {
        title: "External Load",
        graphs: [
            {
                xAccessor: velocityAccessor,
                yAccessor: [totalExternalLoadForceAtCarAccessor, rollingResistanceForceAccessor, inclineForceAccessor, dragForceAccessor],
                config: {
                    title: "External Load Forces at Car vs Vehicle Speed",
                    xAxis: { name: "Vehicle Speed", type: "value", unit: getAxisUnit(velocityAccessor) },
                    yAxis: { name: "Force", type: "value", unit: getAxisUnit(inclineForceAccessor) },
                    seriesNames: ["Total (Car)", "Rolling Resistance", "Incline Force", "Air Resistance"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopLeft,
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
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopLeft,
                }
            }
        ]
    },
    {
        title: "CVT Ratio",
        graphs: [
            {
                xAccessor: timeAccessor,
                yAccessor: [cvtRatioAccessor],
                config: {
                    title: "CVT Ratio vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "CVT Ratio", type: "value", unit: getAxisUnit(cvtRatioAccessor) },
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopRight,
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
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
                }
            },
            {
                xAccessor: timeAccessor,
                yAccessor: [primaryGeometryRateAccessor, secondaryGeometryRateAccessor],
                config: {
                    title: "Primary and Secondary Radius Rate vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Radius Rate", type: "value", unit: getAxisUnit(primaryGeometryRateAccessor) },
                    seriesNames: ["Primary Radius Rate", "Secondary Radius Rate"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
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
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
                }
            }
        ]
    },
    {
        title: "Engine",
        graphs: [
            {
                xAccessor: timeAccessor,
                yAccessor: [engineRpmAccessor],
                config: {
                    title: "Engine RPM vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Engine RPM", type: "value", unit: getAxisUnit(engineRpmAccessor) },
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
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
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopRight,
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
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopRight,
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
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopLeft,
                }
            }
        ]
    },
    {
        title: "Pulley Forces (Overall)",
        graphs: [
            {
                xAccessor: timeAccessor,
                yAccessor: [primaryAxialForceTotalAccessor, secondaryAxialForceTotalAccessor],
                config: {
                    title: "Pulley Total Axial Forces vs Time",
                    xAxis: { name: "Time", type: "value", unit: "s" },
                    yAxis: { name: "Axial Force", type: "value", unit: "N" },
                    seriesNames: ["Primary Total", "Secondary Total"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
                }
            },
            {
                xAccessor: timeAccessor,
                yAccessor: [primaryAxialClampingForceAccessor, secondaryAxialClampingForceAccessor, primaryAxialCentrifugalFromBeltAccessor, secondaryAxialCentrifugalFromBeltAccessor],
                config: {
                    title: "Axial Force Breakdown vs Time",
                    xAxis: { name: "Time", type: "value", unit: "s" },
                    yAxis: { name: "Force", type: "value", unit: "N" },
                    seriesNames: ["Primary Clamping", "Secondary Clamping", "Primary Belt Centrifugal", "Secondary Belt Centrifugal"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
                }
            },
            {
                xAccessor: timeAccessor,
                yAccessor: [cvtAccelerationAccessor],
                config: {
                    title: "CVT Acceleration vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "CVT Acceleration", type: "value", unit: getAxisUnit(cvtAccelerationAccessor) },
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
                }
            }
        ]
    },
    {
        title: "Primary Pulley",
        graphs: [
            {
                xAccessor: timeAccessor,
                yAccessor: [primaryAxialClampingForceAccessor, primaryFlyweightForceAccessor, primarySpringForceAccessor],
                config: {
                    title: "Primary Axial Forces vs Time",
                    xAxis: { name: "Time", type: "value", unit: "s" },
                    yAxis: { name: "Force", type: "value", unit: "N" },
                    seriesNames: ["Net", "Flyweight", "Spring"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
                }
            },
            {
                xAccessor: engineRpmAccessor,
                yAccessor: [rawFlyweightCentrifugalForce, primaryFlyweightForceAccessor],
                config: {
                    title: "Ramp Impact (Raw vs Post-Ramp) vs Engine RPM",
                    xAxis: { name: "Engine RPM", type: "value", unit: getAxisUnit(engineRpmAccessor) },
                    yAxis: { name: "Force", type: "value", unit: "N" },
                    seriesNames: ["Raw Flyweight", "Flyweight"],
                    showXLine: true,
                    showYLine: true,
                    tooltipPosition: TooltipPosition.TopLeft,
                }
            },
            {
                xAccessor: timeAccessor,
                yAccessor: [primaryRampAngleAccessor],
                config: {
                    title: "Primary Ramp Angle vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Ramp Angle", type: "value", unit: "degrees" },
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopRight,
                }
            }
        ]
    },
    {
        title: "Secondary Pulley",
        graphs: [
            {
                xAccessor: timeAccessor,
                yAccessor: [secondaryAxialClampingForceAccessor, secondaryHelixForceAccessor, secondarySpringCompForceAccessor],
                config: {
                    title: "Secondary Axial Forces vs Time",
                    xAxis: { name: "Time", type: "value", unit: "s" },
                    yAxis: { name: "Secondary Force", type: "value", unit: "N" },
                    seriesNames: ["Net", "Helix Force", "Spring Comp Force"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopRight,
                }
            },
            {
                xAccessor: timeAccessor,
                yAccessor: [secondaryHelixFeedbackTorqueAccessor, secondaryHelixSpringTorqueAccessor],
                config: {
                    title: "Secondary Torques vs Time",
                    xAxis: { name: "Time", type: "value", unit: "s" },
                    yAxis: { name: "Torque", type: "value", unit: "N·m" },
                    seriesNames: ["Reactive Feedback", "Torsional Spring"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopRight,
                }
            },
            {
                xAccessor: cvtRatioAccessor,
                yAccessor: [secondaryAxialClampingForceAccessor, secondaryHelixForceAccessor, secondarySpringCompForceAccessor],
                config: {
                    title: "Secondary Axial Forces vs CVT RATIO",
                    xAxis: { name: "CVT RATIO", type: "value", unit: getAxisUnit(cvtRatioAccessor) },
                    yAxis: { name: "Secondary Force", type: "value", unit: "N" },
                    seriesNames: ["Net", "Helix Force", "Spring Comp Force"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopLeft,
                }
            },
            {
                xAccessor: cvtRatioAccessor,
                yAccessor: [secondaryHelixFeedbackTorqueAccessor, secondaryHelixSpringTorqueAccessor],
                config: {
                    title: "Secondary Torques vs CVT RATIO",
                    xAxis: { name: "CVT RATIO", type: "value", unit: getAxisUnit(cvtRatioAccessor) },
                    yAxis: { name: "Torque", type: "value", unit: "N·m" },
                    seriesNames: ["Reactive Feedback", "Torsional Spring"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopLeft,
                }
            }
        ]
    },
    {
        title: "Slip Model",
        graphs: [
            {
                xAccessor: timeAccessor,
                yAccessor: [primary_tau_upperAccessor, primary_tau_lowerAccessor, secondary_tau_positiveAccessor, secondary_tau_negativeAccessor],
                config: {
                    title: "Primary and Secondary Torque Bounds vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Torque", type: "value", unit: getAxisUnit(coupling_torqueAccessor) },
                    seriesNames: ["Primary Upper Bound", "Primary Lower Bound", "Secondary Upper Bound", "Secondary Lower Bound"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
                }
            },
            {
                xAccessor: timeAccessor,
                yAccessor: [tau_upperAccessor, tau_lowerAccessor, coupling_torqueAccessor, torque_demandAccessor],
                config: {
                    title: "Overall Bounds, Coupling, and No-Slip Torque vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Torque", type: "value", unit: getAxisUnit(coupling_torqueAccessor) },
                    seriesNames: ["Overall Upper Bound", "Overall Lower Bound", "Coupling (Final)", "No-Slip Torque"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
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
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopRight,
                }
            }
        ]
    }
];

// Flatten categories into single array for backward compatibility
export const graphConfigs: GraphConfig[] = graphCategories.flatMap(category => category.graphs);
