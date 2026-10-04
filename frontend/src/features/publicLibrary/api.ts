import { api, dataOrThrow } from '@api/transport';
import type { components, paths } from '@api/generated/backend';

type Schema = components['schemas'];
export type PublicationDetail = Schema['PublicationDetail'];
export type PublicationItem = Schema['PublicationItem'];
export type PublicationKind = PublicationItem['kind'];
export type PublicationPreview = Schema['PublicationPreview'];
export type PublishRequest = Schema['PublishRequest'];
export type PublicationPage = Schema['PublicationPage'];
export type ManagedPublication = Schema['ManagedPublication'];
export type CopyOrigin = Schema['CopyOrigin'];
type BrowseQuery = NonNullable<
  paths['/api/v1/publications']['get']['parameters']['query']
>;

export const browsePublications = async (
  query: BrowseQuery,
  signal?: AbortSignal,
) =>
  dataOrThrow(
    await api.GET('/api/v1/publications', { params: { query }, signal }),
  );
export const getPublication = async (id: string, signal?: AbortSignal) =>
  dataOrThrow(
    await api.GET('/api/v1/publications/{publication_id}', {
      params: { path: { publication_id: id } },
      signal,
    }),
  );
export const publicationMetadata = async () =>
  dataOrThrow(await api.GET('/api/v1/publications/metadata'));
export const previewPublication = async (kind: PublicationKind, id: string) =>
  dataOrThrow(
    await api.GET('/api/v1/publications/preview/{kind}/{object_id}', {
      params: { path: { kind, object_id: id } },
    }),
  );
export const managePublications = async (kind: PublicationKind, id: string) =>
  dataOrThrow(
    await api.GET('/api/v1/publications/manage/{kind}/{object_id}', {
      params: { path: { kind, object_id: id } },
    }),
  ).items;
export const publish = async (
  kind: PublicationKind,
  id: string,
  body: PublishRequest,
) =>
  dataOrThrow(
    await api.POST('/api/v1/publications/publish/{kind}/{object_id}', {
      params: { path: { kind, object_id: id } },
      body,
    }),
  );
export const changePublicationAccess = async (
  id: string,
  body: Schema['PublicationAccessRequest'],
) =>
  dataOrThrow(
    await api.PATCH('/api/v1/publications/{publication_id}/access', {
      params: { path: { publication_id: id } },
      body,
    }),
  );
export const copyPublication = async (
  id: string,
  body: Schema['CopyConfiguration'],
) =>
  dataOrThrow(
    await api.POST('/api/v1/publications/{publication_id}/copy', {
      params: { path: { publication_id: id } },
      body,
    }),
  );
export const comparePublications = async (before: string, after: string) =>
  dataOrThrow(
    await api.GET('/api/v1/publications/compare', {
      params: { query: { before, after } },
    }),
  );
export const getCopyOrigin = async (
  kind: Schema['PhysicalItem']['kind'],
  id: string,
) =>
  dataOrThrow(
    await api.GET('/api/v1/publications/origin/{kind}/{object_id}', {
      params: { path: { kind, object_id: id } },
    }),
  );

export function sourceLink(value: string) {
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}
