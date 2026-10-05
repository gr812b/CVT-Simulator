import { api, dataOrThrow } from '@api/transport';
import type { components, paths } from '@api/generated/backend';

type Schema = components['schemas'];
export type PhysicalKind = Schema['PhysicalItem']['kind'];
export type PhysicalDocument = Schema['PhysicalDetail']['document'];
export type PhysicalDetail = Schema['PhysicalDetail'];
export type PhysicalSelection = Schema['PhysicalSelection'];
export type PhysicalItem = Schema['PhysicalItem'];
export type PhysicalField = Schema['PhysicalField'];
export type PhysicalValidation = Schema['CaseValidation'];
export type PhysicalResolvedCase = NonNullable<
  Schema['PhysicalValidationResponse']['resolved_simulation_case']
>;
type PhysicalScope = NonNullable<
  paths['/api/v1/physical-library/items/{kind}']['get']['parameters']['query']
>['scope'];
export type PhysicalDifference = Schema['PhysicalDifference'];
export type PhysicalUpdatePreview = Schema['PhysicalUpdatePreview'];
export type EngineData = Schema['EngineData'];
export type BeltData = Schema['BeltData'];
export type BeltSection = Schema['BeltSection'];
export async function resolveBeltSection(
  body: Schema['BeltSectionSolveRequest'],
  signal?: AbortSignal,
) {
  return dataOrThrow(
    await api.POST('/api/v1/physical-library/belt-section/resolve', {
      body,
      signal,
    }),
  );
}
export type CvtData = Schema['CvtData'];
export type VehicleData = Schema['VehicleData'];
export type EngineChoice = Schema['EngineChoice'];
export type BeltChoice = Schema['BeltChoice'];
export type CvtChoice = Schema['CvtChoice'];
export type SetupData = Schema['SetupData'];
export type PhysicalMetadata = Pick<
  PhysicalDocument,
  'name' | 'description' | 'source_label' | 'source_url' | 'source_notes'
>;

export const kindLabels: Record<PhysicalKind, string> = {
  setups: 'Vehicle setups',
  engines: 'Engines',
  belts: 'Belts',
  cvts: 'CVTs',
};
export const singularLabels: Record<PhysicalKind, string> = {
  setups: 'vehicle setup',
  engines: 'engine',
  belts: 'belt',
  cvts: 'CVT',
};
export function isPhysicalKind(
  value: string | undefined,
): value is PhysicalKind {
  return (
    value !== undefined &&
    Object.prototype.hasOwnProperty.call(kindLabels, value)
  );
}

export async function listPhysical(
  kind: PhysicalKind,
  scope: PhysicalScope = 'own',
  includeArchived = false,
  signal?: AbortSignal,
) {
  return dataOrThrow(
    await api.GET('/api/v1/physical-library/items/{kind}', {
      params: {
        path: { kind },
        query: { scope, include_archived: includeArchived },
      },
      signal,
    }),
  ).items;
}
export async function getPhysical(
  kind: PhysicalKind,
  id: string,
  revisionId?: string,
  signal?: AbortSignal,
) {
  return dataOrThrow(
    await api.GET('/api/v1/physical-library/items/{kind}/{object_id}', {
      params: {
        path: { kind, object_id: id },
        query: { revision_id: revisionId },
      },
      signal,
    }),
  );
}
export async function physicalTemplate(
  kind: PhysicalKind,
  signal?: AbortSignal,
) {
  return dataOrThrow(
    await api.GET('/api/v1/physical-library/templates/{kind}', {
      params: { path: { kind } },
      signal,
    }),
  ).document;
}
export async function physicalMetadata(signal?: AbortSignal) {
  return dataOrThrow(
    await api.GET('/api/v1/physical-library/metadata', { signal }),
  );
}
export async function savePhysical(
  document: PhysicalDocument,
  expected: string | null,
  id?: string,
  note = '',
) {
  const body: Schema['PhysicalSaveRequest'] = {
    document,
    expected_revision_id: expected,
    change_note: note,
  };
  return id
    ? dataOrThrow(
        await api.PUT('/api/v1/physical-library/items/{kind}/{object_id}', {
          params: { path: { kind: document.kind, object_id: id } },
          body,
        }),
      )
    : dataOrThrow(
        await api.POST('/api/v1/physical-library/items/{kind}', {
          params: { path: { kind: document.kind } },
          body,
        }),
      );
}
export async function copyPhysical(
  kind: PhysicalKind,
  revisionId: string,
  name?: string,
) {
  return dataOrThrow(
    await api.POST(
      '/api/v1/physical-library/revisions/{kind}/{revision_id}/copy',
      {
        params: { path: { kind, revision_id: revisionId } },
        body: { name },
      },
    ),
  );
}
export async function restorePhysical(
  kind: PhysicalKind,
  id: string,
  revisionId: string,
  expected: string,
) {
  return dataOrThrow(
    await api.POST(
      '/api/v1/physical-library/items/{kind}/{object_id}/restore',
      {
        params: { path: { kind, object_id: id } },
        body: { revision_id: revisionId, expected_revision_id: expected },
      },
    ),
  );
}
export async function comparePhysical(
  kind: PhysicalKind,
  id: string,
  from: string,
  to: string,
) {
  return dataOrThrow(
    await api.GET('/api/v1/physical-library/items/{kind}/{object_id}/compare', {
      params: {
        path: { kind, object_id: id },
        query: { from_revision_id: from, to_revision_id: to },
      },
    }),
  ).differences;
}
export async function previewUpdate(
  kind: PhysicalKind,
  id: string,
  update: PhysicalDetail['updates'][number],
) {
  return dataOrThrow(
    await api.GET(
      '/api/v1/physical-library/items/{kind}/{object_id}/update-preview',
      {
        params: {
          path: { kind, object_id: id },
          query: {
            component: update.component,
            revision_id: update.available_revision_id,
          },
        },
      },
    ),
  );
}
export async function archivePhysical(item: PhysicalItem, archived: boolean) {
  return dataOrThrow(
    await api.POST(
      '/api/v1/physical-library/items/{kind}/{object_id}/archive',
      {
        params: { path: { kind: item.kind, object_id: item.id } },
        body: { expected_revision_id: item.revision_id, archived },
      },
    ),
  );
}
export async function validatePhysical(document: PhysicalDocument) {
  return dataOrThrow(
    await api.POST('/api/v1/physical-library/validate', { body: { document } }),
  );
}
export async function importCurve(body: Schema['CurveImportRequest']) {
  return dataOrThrow(
    await api.POST('/api/v1/physical-library/engine-curve/import', { body }),
  ).points;
}
