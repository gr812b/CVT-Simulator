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

// Basic kinematics accessors
export const timeAccessor: AccessorStrategy = (point) => point.time;
const positionAccessor: AccessorStrategy = (point) => point.derived_state.car_position;
const velocityAccessor: AccessorStrategy = (point) => point.derived_state.car_velocity;
const accelerationAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.ω_s_dot;

// Drivetrain torque accessors
const torquePrimaryAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.tau_p;
const torqueSecondaryAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.tau_s;
const loadTorqueAtWheels: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.external_load_breakdown.net_torque_at_secondary;

// Engine accessors
const engineRpmAccessor: AccessorStrategy = (point) => point.derived_state.engine_angular_velocity;
const engineTorqueAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.engine_breakdown.engine_torque;
const enginePowerAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.engine_breakdown.engine_power;

// CVT geometry accessors
const cvtRatioAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.effective_cvt_ratio;
const cvtRatioRateOfChangeAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.effective_cvt_ratio_rate_of_change;
const primaryOuterRadiusAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.primary_outer_radius;
const primaryOuterRadiusRateAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.primary_radius_rate_of_change;
const primaryEffectiveRadiusAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.primary_effective_radius;
const secondaryOuterRadiusAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.secondary_outer_radius;
const secondaryOuterRadiusRateAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.secondary_radius_rate_of_change;
const secondaryEffectiveRadiusAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.secondary_effective_radius;
const primaryCentroidRadiusAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.primary_centroid_radius;
const primaryCentroidRadiusRateAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.primary_radius_rate_of_change;
const secondaryCentroidRadiusAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.secondary_centroid_radius;
const secondaryCentroidRadiusRateAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.secondary_radius_rate_of_change;
const primaryWrapAngleAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.primary_wrap_angle;
const secondaryWrapAngleAccessor: AccessorStrategy = (point) => point.contact_breakdown.geometry.secondary_wrap_angle;

// Shift and slip accessors
const cvtAccelerationAccessor: AccessorStrategy = (point) => point.contact_breakdown.shift.acceleration;

// Slip model accessors
const torque_demandAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.no_slip.tau_p_ns;
const secondaryTorqueDemandAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.no_slip.tau_s_ns;
const primaryTorqueUpperAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.admissibility.primary_tau_p_stick_upper;
const primaryTorqueLowerAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.admissibility.primary_tau_p_stick_lower;
const secondaryTorqueUpperAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.admissibility.secondary_tau_stick_upper;
const secondaryTorqueLowerAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.admissibility.secondary_tau_stick_lower;
const simulationModeNormalAccessor: AccessorStrategy = (point) => point.mode === 'normal' ? 1 : 0;
const simulationModeFullShiftAccessor: AccessorStrategy = (point) => point.mode === 'full_shift' ? 1 : 0;
const simulationModeMidShiftAccessor: AccessorStrategy = (point) => point.mode === 'mid_shift' ? 1 : 0;
const branchNoSlipAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.branch === 'NO_SLIP' ? 1 : 0;
const branchPrimarySlipAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.branch === 'PRIMARY_SLIP' ? 1 : 0;
const branchSecondarySlipAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.branch === 'SECONDARY_SLIP' ? 1 : 0;
const branchBothSlipAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.branch === 'BOTH_SLIP' ? 1 : 0;
const primaryRelativeVelocityAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.primary_relative_speed;
const secondaryRelativeVelocityAccessor: AccessorStrategy = (point) => point.contact_breakdown.contact.slip_metrics.secondary_relative_speed;
const beltSpeedAccessor: AccessorStrategy = (point) => point.state.v_b;
const primaryAngularAccelerationAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.ω_p_dot;
const secondaryAngularAccelerationAccessor: AccessorStrategy = (point) => point.contact_breakdown.drivetrain.ω_s_dot;
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
    [torquePrimaryAccessor, 'torque'],
    [torqueSecondaryAccessor, 'torque'],
    [cvtRatioAccessor, 'dimensionless'],
    [cvtRatioRateOfChangeAccessor, 'dimensionless_rate'],
    [primaryOuterRadiusAccessor, 'distance'],
    [primaryOuterRadiusRateAccessor, 'velocity'],
    [primaryEffectiveRadiusAccessor, 'distance'],
    [secondaryOuterRadiusAccessor, 'distance'],
    [secondaryOuterRadiusRateAccessor, 'velocity'],
    [secondaryEffectiveRadiusAccessor, 'distance'],
    [primaryCentroidRadiusAccessor, 'distance'],
    [primaryCentroidRadiusRateAccessor, 'velocity'],
    [secondaryCentroidRadiusAccessor, 'distance'],
    [secondaryCentroidRadiusRateAccessor, 'velocity'],
    [primaryWrapAngleAccessor, 'angle'],
    [secondaryWrapAngleAccessor, 'angle'],
    [engineRpmAccessor, 'angular_velocity'],
    [engineTorqueAccessor, 'torque'],
    [enginePowerAccessor, 'power'],
    [primaryTorqueUpperAccessor, 'torque'],
    [primaryTorqueLowerAccessor, 'torque'],
    [secondaryTorqueUpperAccessor, 'torque'],
    [secondaryTorqueLowerAccessor, 'torque'],
    [simulationModeNormalAccessor, 'dimensionless'],
    [simulationModeFullShiftAccessor, 'dimensionless'],
    [simulationModeMidShiftAccessor, 'dimensionless'],
    [branchNoSlipAccessor, 'dimensionless'],
    [branchPrimarySlipAccessor, 'dimensionless'],
    [branchSecondarySlipAccessor, 'dimensionless'],
    [branchBothSlipAccessor, 'dimensionless'],
    [primaryRelativeVelocityAccessor, 'velocity'],
    [secondaryRelativeVelocityAccessor, 'velocity'],
    [beltSpeedAccessor, 'velocity'],
    [torquePrimaryAccessor, 'torque'],
    [torqueSecondaryAccessor, 'torque'],
    [primaryAngularAccelerationAccessor, 'angular_acceleration'],
    [secondaryAngularAccelerationAccessor, 'angular_acceleration'],
    [torque_demandAccessor, 'torque'],
    [secondaryTorqueDemandAccessor, 'torque'],
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
    [loadTorqueAtWheels, 'torque'],
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
                yAccessor: [torqueSecondaryAccessor, loadTorqueAtWheels],
                config: {
                    title: "Torques at Wheels vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Torque", type: "value", unit: getAxisUnit(torqueSecondaryAccessor) },
                    seriesNames: ["Secondary Torque", "Load Torque at Secondary"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopRight,
                }
            },
            {
                xAccessor: timeAccessor,
                yAccessor: [torquePrimaryAccessor, engineTorqueAccessor],
                config: {
                    title: "Torques at Engine vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Torque", type: "value", unit: getAxisUnit(torquePrimaryAccessor) },
                    seriesNames: ["Primary Torque", "Engine Torque"],
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
                yAccessor: [primaryOuterRadiusRateAccessor, secondaryOuterRadiusRateAccessor],
                config: {
                    title: "Primary and Secondary Outer Radius Rate vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Radius Rate", type: "value", unit: getAxisUnit(primaryOuterRadiusRateAccessor) },
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
                yAccessor: [engineTorqueAccessor, primaryTorqueUpperAccessor],
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
                yAccessor: [torquePrimaryAccessor, primaryTorqueUpperAccessor, primaryTorqueLowerAccessor, torque_demandAccessor],
                config: {
                    title: "Primary Torque and Bounds vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Torque", type: "value", unit: getAxisUnit(torquePrimaryAccessor) },
                    seriesNames: ["tau_p", "Primary Upper Bound", "Primary Lower Bound", "tau_p_ns"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
                }
            },
            {
                xAccessor: timeAccessor,
                yAccessor: [torqueSecondaryAccessor, secondaryTorqueUpperAccessor, secondaryTorqueLowerAccessor, secondaryTorqueDemandAccessor],
                config: {
                    title: "Secondary Torque and Bounds vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Torque", type: "value", unit: getAxisUnit(torqueSecondaryAccessor) },
                    seriesNames: ["tau_s", "Secondary Upper Bound", "Secondary Lower Bound", "tau_s_ns"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
                }
            },
            {
                xAccessor: timeAccessor,
                yAccessor: [branchNoSlipAccessor, branchPrimarySlipAccessor, branchSecondarySlipAccessor, branchBothSlipAccessor],
                config: {
                    title: "Slip Branch State vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Branch Active", type: "value", unit: getAxisUnit(branchNoSlipAccessor) },
                    seriesNames: ["No Slip", "Primary Slip", "Secondary Slip", "Both Slip"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
                }
            },
            {
                xAccessor: timeAccessor,
                yAccessor: [primaryRelativeVelocityAccessor, secondaryRelativeVelocityAccessor],
                config: {
                    title: "Primary and Secondary Relative Velocity vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Relative Velocity", type: "value", unit: getAxisUnit(primaryRelativeVelocityAccessor) },
                    seriesNames: ["Primary Relative Velocity", "Secondary Relative Velocity"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopRight,
                }
            },
            {
                xAccessor: timeAccessor,
                yAccessor: [beltSpeedAccessor],
                config: {
                    title: "Belt Speed vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Belt Speed", type: "value", unit: getAxisUnit(beltSpeedAccessor) },
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.TopRight,
                }
            },
            {
                xAccessor: timeAccessor,
                yAccessor: [torquePrimaryAccessor, torqueSecondaryAccessor],
                config: {
                    title: "Primary and Secondary Torque vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Torque", type: "value", unit: getAxisUnit(torquePrimaryAccessor) },
                    seriesNames: ["Primary Torque", "Secondary Torque"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
                }
            },
            {
                xAccessor: timeAccessor,
                yAccessor: [primaryAngularAccelerationAccessor, secondaryAngularAccelerationAccessor],
                config: {
                    title: "Primary and Secondary Angular Acceleration vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Angular Acceleration", type: "value", unit: getAxisUnit(primaryAngularAccelerationAccessor) },
                    seriesNames: ["Primary Angular Acceleration", "Secondary Angular Acceleration"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
                }
            }
        ]
    },
    {
        title: "Simulation Mode",
        graphs: [
            {
                xAccessor: timeAccessor,
                yAccessor: [simulationModeNormalAccessor, simulationModeFullShiftAccessor, simulationModeMidShiftAccessor],
                config: {
                    title: "Simulation Mode vs Time",
                    xAxis: { name: "Time", type: "value", unit: getAxisUnit(timeAccessor) },
                    yAxis: { name: "Mode Active", type: "value", unit: getAxisUnit(simulationModeNormalAccessor) },
                    seriesNames: ["normal", "full_shift", "mid_shift"],
                    showXLine: true,
                    showYLine: false,
                    tooltipPosition: TooltipPosition.BottomRight,
                }
            }
        ]
    }
];

// Flatten categories into single array for backward compatibility
export const graphConfigs: GraphConfig[] = graphCategories.flatMap(category => category.graphs);
