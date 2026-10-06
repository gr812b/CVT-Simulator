import { api, dataOrThrow } from '@api/transport';
import type { components } from '@api/generated/backend';

type Schema = components['schemas'];
export type ExperimentDocument = Schema['ExperimentDetail']['document'];
export type ExperimentDetail = Schema['ExperimentDetail'];
export type ExperimentItem = Schema['ExperimentItem'];
export type ExperimentKind = ExperimentItem['kind'];
export type Scenario = Schema['ScenarioDocument'];
export type Tune = Schema['TuneDocument'];
export type TuneSurface = Schema['TuneSurface'];
export type TunePreview = Schema['TuneScenePreview'];
export type TuneProfileTrace = Schema['TuneProfileTrace'];
export type TuneField = TuneSurface['fields'][number];
export type Road = Schema['SpatialRoad'];
export type RoadFeature = Road['features'][number];
export type RoadPoint = Schema['RoadPoint'];
export type RoadResolution = Schema['RoadResolution'];
export type ExperimentMetadata = Schema['ExperimentMetadata'];
export type ExperimentSelection = Schema['ExperimentSelection'];
export type ExperimentPreview = Schema['ExperimentPreview'];
export type SubmitExperiment = Schema['SubmitExperiment'];
export type RunStatus = Schema['RunStatusResponse'];
export type RunActivity = Schema['RunActivity'];

export const getExperimentMetadata = async () =>
  dataOrThrow(await api.GET('/api/v1/experiments/metadata'));
export const getTuneSurface = async (cvt: string) =>
  dataOrThrow(
    await api.GET('/api/v1/experiments/tuning/{cvt_revision_id}', {
      params: { path: { cvt_revision_id: cvt } },
    }),
  );
export const resolveRoad = async (body: Road, signal?: AbortSignal) =>
  dataOrThrow(
    await api.POST('/api/v1/experiments/road/resolve', { body, signal }),
  );
export const listExperiments = async (
  kind: ExperimentKind,
  cvtObjectId?: string,
  options?: {
    authorId?: string;
    signal?: AbortSignal;
    includeArchived?: boolean;
  },
) =>
  dataOrThrow(
    await api.GET('/api/v1/experiments/items/{kind}', {
      signal: options?.signal,
      params: {
        path: { kind },
        query: {
          include_archived: options?.includeArchived ?? true,
          cvt_object_id: cvtObjectId,
          author_id: options?.authorId,
        },
      },
    }),
  ).items;
export const getExperiment = async (id: string, revision?: string) =>
  dataOrThrow(
    await api.GET('/api/v1/experiments/items/{object_id}/detail', {
      params: { path: { object_id: id }, query: { revision_id: revision } },
    }),
  );
export async function saveExperiment(
  document: ExperimentDocument,
  detail: ExperimentDetail | null,
  asNew = false,
) {
  const own = detail?.item.owned && !asNew;
  const body: Schema['ExperimentSave'] = {
    document,
    expected_revision_id: own ? detail.item.revision_id : null,
    change_note: '',
  };
  return own
    ? dataOrThrow(
        await api.PUT('/api/v1/experiments/items/{object_id}', {
          params: { path: { object_id: detail.item.id } },
          body,
        }),
      ).detail
    : dataOrThrow(await api.POST('/api/v1/experiments/items', { body })).detail;
}
export const archiveExperiment = async (detail: ExperimentDetail) =>
  dataOrThrow(
    await api.POST('/api/v1/experiments/items/{object_id}/archive', {
      params: { path: { object_id: detail.item.id } },
      body: {
        expected_revision_id: detail.item.revision_id,
        archived: !detail.item.archived,
      },
    }),
  );
export const restoreExperiment = async (
  detail: ExperimentDetail,
  revision: string,
) =>
  dataOrThrow(
    await api.POST('/api/v1/experiments/items/{object_id}/restore', {
      params: { path: { object_id: detail.item.id } },
      body: {
        expected_revision_id: detail.item.revision_id,
        revision_id: revision,
      },
    }),
  ).detail;
export const compareExperiments = async (before: string, after: string) =>
  dataOrThrow(
    await api.GET('/api/v1/experiments/compare', {
      params: { query: { before, after } },
    }),
  ).differences;
export const previewExperiment = async (
  body: ExperimentSelection,
  signal?: AbortSignal,
) =>
  dataOrThrow(await api.POST('/api/v1/experiments/preview', { body, signal }));
export const submitExperiment = async (body: SubmitExperiment) =>
  dataOrThrow(await api.POST('/api/v1/experiments/runs', { body }));
export const getActivity = async () =>
  dataOrThrow(await api.GET('/api/v1/runs/activity'));
export const getRun = async (id: string) =>
  dataOrThrow(
    await api.GET('/api/v1/runs/{run_id}', {
      params: { path: { run_id: id } },
    }),
  );
export const listRuns = async (signal?: AbortSignal, limit = 20) =>
  dataOrThrow(
    await api.GET('/api/v1/runs', { params: { query: { limit } }, signal }),
  ).items ?? [];
export const cancelRun = async (id: string) =>
  dataOrThrow(
    await api.POST('/api/v1/runs/{run_id}/cancel', {
      params: { path: { run_id: id } },
    }),
  );
export const rerun = async (id: string, key: string) =>
  dataOrThrow(
    await api.POST('/api/v1/runs/{run_id}/rerun', {
      params: { path: { run_id: id } },
      body: { request_key: key },
    }),
  );
export async function readNotice(id: string) {
  const response = await api.POST('/api/v1/runs/notices/{notice_id}/read', {
    params: { path: { notice_id: id } },
  });
  if (!response.response.ok) dataOrThrow(response);
}
export const message = (error: unknown) =>
  error instanceof Error
    ? error.message
    : 'This operation could not be completed.';
export const isActive = (run: RunStatus) =>
  run.status === 'queued' || run.status === 'running';

export const setDefaultTune = async (surface: TuneSurface, tuneId: string) =>
  dataOrThrow(
    await api.PUT('/api/v1/experiments/tuning/{cvt_revision_id}/default', {
      params: { path: { cvt_revision_id: surface.cvt_revision_id } },
      body: { tune_id: tuneId, expected_tune_id: surface.default_tune.item.id },
    }),
  );
export const previewTune = async (value: Tune, signal?: AbortSignal) =>
  dataOrThrow(
    await api.POST('/api/v1/experiments/tuning/preview', {
      body: { cvt_revision_id: value.cvt_revision_id, values: value.values },
      signal,
    }),
  );
