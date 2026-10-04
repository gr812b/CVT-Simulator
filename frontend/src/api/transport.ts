import createClient from 'openapi-fetch';
import type { paths } from './generated/backend';

export const baseUrl = (
  import.meta.env.VITE_API_BASE_URL ?? window.location.origin
).replace(/\/+$/, '');
let csrfToken: string | null = null;
export const SESSION_EXPIRED = 'cinder:session-expired';
const anonymousAuthRoutes = new Set<keyof paths>([
  '/api/v1/auth/login',
  '/api/v1/auth/register',
  '/api/v1/auth/session',
  '/api/v1/auth/forgot-password',
  '/api/v1/auth/reset-password',
]);

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

/** All transports share cookie, CSRF, and expired-session handling. */
export async function authenticatedFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const requestToken = csrfToken;
  const request = new Request(input, init);
  request.headers.set('X-Cinder-Client', 'web');
  if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method) && csrfToken) {
    request.headers.set('X-CSRF-Token', csrfToken);
  }
  const response = await fetch(
    new Request(request, { credentials: 'include' }),
  );
  if (
    response.status === 401 &&
    requestToken === csrfToken &&
    !anonymousAuthRoutes.has(new URL(request.url).pathname as keyof paths)
  ) {
    window.dispatchEvent(new Event(SESSION_EXPIRED));
  }
  return response;
}

export const api = createClient<paths>({ baseUrl, fetch: authenticatedFetch });

export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = 'ApiClientError';
  }
}

export function dataOrThrow<T>(result: {
  data?: T;
  error?: unknown;
  response: Response;
}): T {
  if (result.data !== undefined && result.response.ok) return result.data;
  const payload = result.error;
  let message = 'The request could not be completed. Please try again.';
  if (typeof payload === 'object' && payload !== null && 'error' in payload) {
    const error = payload.error;
    if (
      typeof error === 'object' &&
      error !== null &&
      'message' in error &&
      typeof error.message === 'string'
    )
      message = error.message;
  }
  if (
    result.response.status === 422 &&
    typeof payload === 'object' &&
    payload !== null &&
    'detail' in payload &&
    Array.isArray(payload.detail)
  ) {
    const errors = payload.detail.flatMap((entry: unknown) => {
      if (
        typeof entry !== 'object' ||
        entry === null ||
        !('msg' in entry) ||
        typeof entry.msg !== 'string'
      )
        return [];
      const location =
        'loc' in entry && Array.isArray(entry.loc)
          ? entry.loc.filter((value) => value !== 'body').join(' › ')
          : '';
      return [`${location ? `${location}: ` : ''}${entry.msg}`];
    });
    if (errors.length) message = errors.join('\n');
  }
  throw new ApiClientError(message, result.response.status, payload);
}
