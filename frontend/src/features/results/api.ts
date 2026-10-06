import { api, dataOrThrow } from '@api/transport';
import type { components, paths } from '@api/generated/backend';

type Schema = components['schemas'];
export type RunInspection = Schema['RunInspection'];
export type RunHistoryPage = Schema['RunHistoryPage'];
export type RunSeries = Schema['RunSeries'];
export type ResultMetric = Schema['ResultMetric'];
export type HistoryQuery = NonNullable<
  paths['/api/v1/run-history']['get']['parameters']['query']
>;
export type ExportKind =
  paths['/api/v1/runs/{run_id}/exports/{kind}']['get']['parameters']['path']['kind'];

export const getHistory = async (query: HistoryQuery, signal?: AbortSignal) =>
  dataOrThrow(
    await api.GET('/api/v1/run-history', { params: { query }, signal }),
  );
export const inspectRun = async (id: string) =>
  dataOrThrow(
    await api.GET('/api/v1/runs/{run_id}/inspection', {
      params: { path: { run_id: id } },
    }),
  );
export const getSeries = async (
  id: string,
  resolution: RunSeries['resolution'],
  signal?: AbortSignal,
) =>
  dataOrThrow(
    await api.GET('/api/v1/runs/{run_id}/series', {
      params: { path: { run_id: id }, query: { resolution } },
      signal,
    }),
  );
export const getFrozenInput = async (id: string) =>
  dataOrThrow(
    await api.GET('/api/v1/runs/{run_id}/input', {
      params: { path: { run_id: id } },
    }),
  );
export const renameRun = async (id: string, body: Schema['RenameRun']) =>
  dataOrThrow(
    await api.PATCH('/api/v1/runs/{run_id}/name', {
      params: { path: { run_id: id } },
      body,
    }),
  );
export const getRunExperiment = async (id: string) =>
  dataOrThrow(
    await api.GET('/api/v1/runs/{run_id}/experiment', {
      params: { path: { run_id: id } },
    }),
  );
export const exportRun = async (id: string, kind: ExportKind) =>
  dataOrThrow(
    await api.GET('/api/v1/runs/{run_id}/exports/{kind}', {
      params: { path: { run_id: id, kind } },
      parseAs: 'blob',
    }),
  );

export function formatMetric(metric: ResultMetric) {
  const value = metric.value;
  return value === null
    ? 'Unavailable'
    : `${typeof value === 'number' ? new Intl.NumberFormat(undefined, { maximumSignificantDigits: 5 }).format(value) : String(value)}${metric.unit ? ` ${metric.unit}` : ''}`;
}
