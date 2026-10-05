import type { components } from '@api/generated/backend';
import { api, dataOrThrow } from '@api/transport';
export type ForcePlayback = components['schemas']['ForcePlayback'];
export type ForceTrack = components['schemas']['ForceTrack'];
export type ForceSample = components['schemas']['ForceVectorSample'];
export async function loadForces(
  source: string,
  signal?: AbortSignal,
): Promise<ForcePlayback> {
  return source === 'demo'
    ? dataOrThrow(await api.GET('/api/v1/demo/forces', { signal }))
    : dataOrThrow(
        await api.GET('/api/v1/runs/{run_id}/forces', {
          params: { path: { run_id: source } },
          signal,
        }),
      );
}
