import type { PhysicalKind } from './api';

/** Physical detail routes are shared by public readers and workspace owners. */
export function physicalDetailPath(kind: PhysicalKind, objectId: string, revisionId?: string): string {
  const path = `/library/${kind}/${encodeURIComponent(objectId)}`;
  return revisionId ? `${path}?${new URLSearchParams({ revision: revisionId })}` : path;
}
