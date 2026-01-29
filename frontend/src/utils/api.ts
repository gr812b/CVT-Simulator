import createClient from 'openapi-fetch';
import type { paths, operations, components } from '@types'; // from openapi-typescript

const client = createClient<paths>({ baseUrl: import.meta.env.VITE_API_BASE_URL ?? '' });

// Types pulled straight from your schema:
export type RunBody = NonNullable<operations['run_run_post']['requestBody']>['content']['application/json'];
export type RunResponse =
  operations['run_run_post']['responses']['200']['content']['application/json'];

export async function runSimulation(body?: RunBody): Promise<RunResponse> {
  const { data, error } = await client.POST('/run', { body: body ?? {} });
  if (error) throw error;
  return data!;
}

// Streaming endpoint types
export type RunStreamBody = NonNullable<operations['run_stream_run_stream_post']['requestBody']>['content']['application/json'];
// TODO: Do we need these 3 types separately?
export type StreamProgressMessage = components['schemas']['StreamProgressMessage'];
export type StreamCompleteMessage = components['schemas']['StreamCompleteMessage'];
export type StreamErrorMessage = components['schemas']['StreamErrorMessage'];
// Use the union type directly from the operation response
export type StreamMessage = operations['run_stream_run_stream_post']['responses']['200']['content']['application/json'];

/**
 * Run simulation with streaming progress updates.
 * Uses the /run/stream endpoint which returns NDJSON (newline-delimited JSON).
 * @param body - Simulation parameters (same as regular run endpoint)
 * @param onProgress - Callback for progress updates (0-100)
 * @returns Promise that resolves with the final simulation result
 */
export async function runSimulationStreaming(
  body?: RunStreamBody,
  onProgress?: (percent: number) => void
): Promise<RunResponse> {
  // TODO: Find a better way to encapsulate this
  // We can't use CLIENT.POST as it doesn't have support for streaming
  const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, ''); // Remove trailing slashes
  
  console.log('Starting streaming request to:', `${baseUrl}/run/stream`);
  
  const response = await fetch(`${baseUrl}/run/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/x-ndjson',
    },
    body: JSON.stringify(body ?? {}),
  });

  // TODO: Convert commented logs into notifications once added
  // console.log('Response status:', response.status, 'Headers:', Object.fromEntries(response.headers.entries()));

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  if (!response.body) {
    throw new Error('No response body');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalResult: RunResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();

    if (done) {
      // console.log('Stream ended');
      break;
    }

    // Decode the chunk and add to buffer
    buffer += decoder.decode(value, { stream: true });

    // Process complete lines (NDJSON - newline delimited)
    const lines = buffer.split('\n');
    buffer = lines.pop() || ''; // Keep incomplete line in buffer

    for (const line of lines) {
      if (!line.trim()) continue;

      try {
        const message: StreamMessage = JSON.parse(line);

        if (message.type === 'progress') {
          if (onProgress) {
            onProgress(message.percent);
          }
        } else if (message.type === 'complete') {
          finalResult = message.data;
        } else if (message.type === 'error') {
          // console.error('Simulation error:', message.message);
          throw new Error(message.message);
        }
      } catch (e) {
        // TODO: Convert to notification
        console.error('Error parsing streaming message:', e);
      }
    }
  }

  if (!finalResult) {
    throw new Error('Simulation did not return a result');
  }

  return finalResult;
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
