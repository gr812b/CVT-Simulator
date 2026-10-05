import { api, dataOrThrow } from '@api/transport';
import type { components, paths } from '@api/generated/backend';

export type SchoolCatalog = components['schemas']['SchoolCatalog'];
export type PublicUserPage = components['schemas']['PublicUserPage'];
type Query = paths['/api/v1/community/users']['get']['parameters']['query'];
let schools: Promise<SchoolCatalog> | undefined;
export function getSchools() {
  schools ??= api
    .GET('/api/v1/community/schools')
    .then(dataOrThrow)
    .catch((error) => {
      schools = undefined;
      throw error;
    });
  return schools;
}
export async function getUsers(query: Query, signal?: AbortSignal) {
  return dataOrThrow(
    await api.GET('/api/v1/community/users', { params: { query }, signal }),
  );
}
