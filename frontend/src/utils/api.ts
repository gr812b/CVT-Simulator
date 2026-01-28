import createClient from 'openapi-fetch';
import type { paths, operations } from '@types'; // from openapi-typescript

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

// NDJSON streaming message types
export type StreamProgressMessage = {
  type: 'progress';
  percent: number;
};

export type StreamCompleteMessage = {
  type: 'complete';
  data: RunResponse;
};

export type StreamErrorMessage = {
  type: 'error';
  message: string;
};

export type StreamMessage = StreamProgressMessage | StreamCompleteMessage | StreamErrorMessage;

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

  console.log('Response status:', response.status, 'Headers:', Object.fromEntries(response.headers.entries()));

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

  console.log('Starting to read stream...');

  while (true) {
    const { done, value } = await reader.read();

    if (done) {
      console.log('Stream ended');
      break;
    }

    console.log('Received chunk of size:', value.length);

    // Decode the chunk and add to buffer
    buffer += decoder.decode(value, { stream: true });

    // Process complete lines (NDJSON - newline delimited)
    const lines = buffer.split('\n');
    buffer = lines.pop() || ''; // Keep incomplete line in buffer

    for (const line of lines) {
      if (!line.trim()) continue;

      console.log('Processing line:', line);

      try {
        const message = JSON.parse(line) as StreamMessage;

        if (message.type === 'progress') {
          console.log(`Simulation progress: ${message.percent.toFixed(1)}%`);
          if (onProgress) {
            onProgress(message.percent);
          }
        } else if (message.type === 'complete') {
          console.log('Simulation complete!');
          finalResult = message.data;
        } else if (message.type === 'error') {
          console.error('Simulation error:', message.message);
          throw new Error(message.message);
        }
      } catch (e) {
        console.error('Error parsing streaming message:', e, line);
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
