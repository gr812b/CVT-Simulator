import createClient from 'openapi-fetch';
import type { paths, operations } from '@types'; // from openapi-typescript

const client = createClient<paths>({ baseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000' });

// Types pulled straight from your schema:
export type RunBody = NonNullable<operations['run_run_post']['requestBody']>['content']['application/json'];
export type RunResponse =
  operations['run_run_post']['responses']['200']['content']['application/json'];

export async function runSimulation(body?: RunBody): Promise<RunResponse> {
  const { data, error } = await client.POST('/run', { body: body ?? {} });
  if (error) throw error;
  return data!;
}

export type ConstantsResponse =
  operations['get_constants_constants_get']['responses']['200']['content']['application/json'];

export async function getConstants(): Promise<ConstantsResponse> {
  const { data, error } = await client.GET('/constants');
  if (error) throw error;
  return data!;
}

export type RampPreviewBody = NonNullable<operations['preview_ramp_ramp_preview_post']['requestBody']>['content']['application/json'];
export type RampPreviewResponse =
  operations['preview_ramp_ramp_preview_post']['responses']['200']['content']['application/json'];

export async function previewRamp(body: RampPreviewBody): Promise<RampPreviewResponse> {
  const { data, error } = await client.POST('/ramp/preview', { body });
  if (error) throw error;
  return data!;
}
