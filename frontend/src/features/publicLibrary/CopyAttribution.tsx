import { useEffect, useState } from 'react';
import { Alert, Anchor, Text } from '@mantine/core';
import { Link } from 'react-router-dom';
import { getCopyOrigin, type CopyOrigin } from './api';
import type { PhysicalKind } from '../physicalLibrary/api';

export function CopyAttribution({
  kind,
  objectId,
}: {
  kind: PhysicalKind;
  objectId: string;
}) {
  const [origin, setOrigin] = useState<CopyOrigin | null>(null);
  useEffect(() => {
    let disposed = false;
    void getCopyOrigin(kind, objectId)
      .then((value) => {
        if (!disposed) setOrigin(value);
      })
      .catch(() => {
        /* The physical item remains usable if attribution cannot be loaded. */
      });
    return () => {
      disposed = true;
    };
  }, [kind, objectId]);
  if (!origin) return null;
  return (
    <Alert color="blue" title="Independent copy">
      <Text size="sm">
        Copied {new Date(origin.copied_at).toLocaleDateString()} from{' '}
        {origin.publication_id ? (
          <Anchor component={Link} to={`/catalog/${origin.publication_id}`}>
            a fixed publication
          </Anchor>
        ) : (
          <Anchor component={Link} to={`/runs/${origin.run_id}`}>
            a run’s frozen configuration
          </Anchor>
        )}
        . Changes to the source do not update this item. A publication link may
        become unavailable if its owner withdraws it.
      </Text>
    </Alert>
  );
}
