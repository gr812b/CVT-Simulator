import type { components } from './generated/backend';
import { api, dataOrThrow } from './transport';

export type RampKind = components['schemas']['FixedPivotRamp']['kind'];
export type PackagingZoneSubject = components['schemas']['PackagingZone']['subject'];
export type PackagingZoneRule = components['schemas']['PackagingZone']['rule'];

export type FixedPivotArchitecture = components['schemas']['FixedPivotArchitecture'];

export type PackagingZone = components['schemas']['PackagingZone'];

export type FixedPivotRamp = components['schemas']['FixedPivotRamp'];

export type PrimaryDesignOperating = components['schemas']['PrimaryDesignOperating'];

export type PrimaryDesignDefaults = components['schemas']['PrimaryDesignDefaults'];

export type SampledFieldSet = components['schemas']['SampledFieldSet'];

export type DoubleContactFailureGeometry = components['schemas']['DoubleContactFailureGeometry'];

export type DesignFailure = components['schemas']['DesignFailure'];

export type DesignWarning = components['schemas']['DesignWarning'];

export type ConcreteDesignAnalysis = components['schemas']['ConcreteDesignAnalysis'];

export type ConcreteDesignResponse = components['schemas']['ConcreteDesignResponse'];

export type WorkspacePolygon = components['schemas']['WorkspacePolygon'];

export type ArchitectureFinding = components['schemas']['ArchitectureFinding'];

export type PackagingZoneDiagnostic = components['schemas']['PackagingZoneDiagnostic'];

export type ArchitectureAnalysis = components['schemas']['ArchitectureAnalysis'];

export type PathDomainStationProjection = components['schemas']['PathDomainStationProjection'];

export type HistoryCertifiedRampPath = components['schemas']['HistoryCertifiedRampPath'];

export type PrimaryPathDomainAnalysis = components['schemas']['PrimaryPathDomainAnalysis'];

export type ForceRequirement = Required<components['schemas']['ForceRequirementRequest']>;

export type ConditionedRampSolution = components['schemas']['ConditionedRampSolution'];

export type ConditionedPathDomainAnalysis = components['schemas']['ConditionedPathDomainAnalysis'];

export type AbsoluteForceCapability = components['schemas']['AbsoluteForceCapability'];

export async function getPrimaryDesignDefaults(): Promise<PrimaryDesignDefaults> {
  return dataOrThrow(await api.GET('/api/v1/engineering/fixed-pivot-primary/defaults'));
}

export async function analyzePrimaryArchitecture(
  architecture: FixedPivotArchitecture,
  zones: PackagingZone[],
  reachSampleCount = 361,
  shiftSampleCount = 41,
): Promise<ArchitectureAnalysis> {
  return dataOrThrow(
    await api.POST('/api/v1/engineering/fixed-pivot-primary/architecture/analyze', {
      body: {
        architecture,
        zones,
        reach_sample_count: reachSampleCount,
        shift_sample_count: shiftSampleCount,
      },
    }),
  );
}

export async function analyzeConcretePrimaryDesign(
  architecture: FixedPivotArchitecture,
  ramp: FixedPivotRamp,
  sampleCount = 161,
): Promise<ConcreteDesignAnalysis> {
  return dataOrThrow(
    await api.POST('/api/v1/engineering/fixed-pivot-primary/concrete/analyze', {
      body: { architecture, ramp, sample_count: sampleCount },
    }),
  );
}

export async function evaluateConcretePrimaryDesign(
  analysisId: string,
  operating: PrimaryDesignOperating,
): Promise<ConcreteDesignResponse> {
  return dataOrThrow(
    await api.POST('/api/v1/engineering/fixed-pivot-primary/concrete/response', {
      body: { analysis_id: analysisId, ...operating },
    }),
  );
}

export async function analyzePrimaryPathDomain(
  architecture: FixedPivotArchitecture,
  zones: PackagingZone[],
  options: Omit<
    components['schemas']['FixedPivotPathDomainRequest'],
    'architecture' | 'zones'
  > = {},
): Promise<PrimaryPathDomainAnalysis> {
  return dataOrThrow(
    await api.POST('/api/v1/engineering/fixed-pivot-primary/architecture/path-domain', {
      body: { architecture, zones, ...options },
    }),
  );
}

export async function conditionPrimaryPathDomain(
  domainId: string,
  requirements: ForceRequirement[],
  maxTipMassPerFlyweightKg: number,
  options: Omit<
    components['schemas']['FixedPivotPathDomainConditionRequest'],
    'domain_id' | 'requirements' | 'max_tip_mass_per_flyweight_kg'
  > = {},
): Promise<ConditionedPathDomainAnalysis> {
  return dataOrThrow(
    await api.POST('/api/v1/engineering/fixed-pivot-primary/architecture/path-domain/condition', {
      body: {
        domain_id: domainId,
        requirements,
        max_tip_mass_per_flyweight_kg: maxTipMassPerFlyweightKg,
        ...options,
      },
    }),
  );
}

export type InverseDesignTargetPoint = components['schemas']['InverseDesignTargetPoint'];

export type InverseRampSolution = components['schemas']['InverseRampSolution'];

export type InverseDesignAnalysis = components['schemas']['InverseDesignAnalysis'];

export type ArchitectureShapePoint = components['schemas']['ArchitectureShapePoint'];

export type ArchitectureComparisonWitness = components['schemas']['ArchitectureComparisonWitness'];

export type ArchitectureComparisonAnalysis =
  components['schemas']['ArchitectureComparisonAnalysis'];

export async function inverseDesignPrimaryForceCurve(
  architecture: FixedPivotArchitecture,
  zones: PackagingZone[],
  targetPoints: InverseDesignTargetPoint[],
  shaftSpeedRadS: number,
  maxTipMassPerFlyweightKg: number,
  fixedTipMassPerFlyweightKg: number | null,
  options: Omit<
    components['schemas']['FixedPivotInverseDesignRequest'],
    | 'architecture'
    | 'zones'
    | 'target_points'
    | 'shaft_speed_rad_s'
    | 'max_tip_mass_per_flyweight_kg'
    | 'fixed_tip_mass_per_flyweight_kg'
  > = {},
): Promise<InverseDesignAnalysis> {
  return dataOrThrow(
    await api.POST('/api/v1/engineering/fixed-pivot-primary/inverse-design', {
      body: {
        architecture,
        zones,
        target_points: targetPoints,
        shaft_speed_rad_s: shaftSpeedRadS,
        max_tip_mass_per_flyweight_kg: maxTipMassPerFlyweightKg,
        fixed_tip_mass_per_flyweight_kg: fixedTipMassPerFlyweightKg,
        ...options,
      },
    }),
  );
}

export async function comparePrimaryPathDomains(
  domainIdA: string,
  domainIdB: string,
  options: Omit<
    components['schemas']['FixedPivotPathDomainCompareRequest'],
    'domain_id_a' | 'domain_id_b'
  > = {},
): Promise<ArchitectureComparisonAnalysis> {
  return dataOrThrow(
    await api.POST('/api/v1/engineering/fixed-pivot-primary/architecture/path-domain/compare', {
      body: { domain_id_a: domainIdA, domain_id_b: domainIdB, ...options },
    }),
  );
}

export type ForceShapeTargetPoint = components['schemas']['ForceShapeTargetPoint'];

export type ArchitectureTargetMatch = components['schemas']['ArchitectureTargetMatch'];

export type ArchitectureTargetComparisonAnalysis =
  components['schemas']['ArchitectureTargetComparisonAnalysis'];

export async function comparePrimaryPathDomainsToTarget(
  domainIdA: string,
  domainIdB: string,
  targetPoints: ForceShapeTargetPoint[],
  options: Omit<
    components['schemas']['FixedPivotPathDomainCompareTargetRequest'],
    'domain_id_a' | 'domain_id_b' | 'target_points'
  > = {},
): Promise<ArchitectureTargetComparisonAnalysis> {
  return dataOrThrow(
    await api.POST(
      '/api/v1/engineering/fixed-pivot-primary/architecture/path-domain/compare-target',
      {
        body: {
          domain_id_a: domainIdA,
          domain_id_b: domainIdB,
          target_points: targetPoints,
          ...options,
        },
      },
    ),
  );
}
