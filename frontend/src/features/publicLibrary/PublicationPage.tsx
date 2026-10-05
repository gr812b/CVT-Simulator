import { useEffect, useState } from 'react';
import { Alert, Container } from '@mantine/core';
import { Navigate, useLocation, useParams } from 'react-router-dom';
import { PageLoading } from '@components/loadingOverlay/PageLoading';
import { getPublication } from './api';
import { message } from '../experiments/api';
export function PublicationPage() {
  const { publicationId } = useParams();
  const { hash } = useLocation();
  return (
    <PublicationRedirect
      key={`${publicationId}${hash}`}
      publicationId={publicationId ?? ''}
      hash={hash}
    />
  );
}

function PublicationRedirect({
  publicationId,
  hash,
}: {
  publicationId: string;
  hash: string;
}) {
  const [target, setTarget] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void getPublication(publicationId ?? '', controller.signal)
      .then(({ item }) => {
        if (!controller.signal.aborted)
          setTarget(
            `/library/${item.kind}/${item.source_object_id}?revision=${item.source_revision_id}${hash}`,
          );
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(message(cause));
      });
    return () => controller.abort();
  }, [publicationId, hash]);
  if (error)
    return (
      <Container py="xl">
        <Alert color="red" title="Configuration unavailable">
          {error}
        </Alert>
      </Container>
    );
  return target ? (
    <Navigate to={target} replace />
  ) : (
    <PageLoading message="Loading configuration…" />
  );
}
