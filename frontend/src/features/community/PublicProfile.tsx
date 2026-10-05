import { useEffect, useState } from 'react';
import { Alert, Anchor, Avatar, Group, Text, Title } from '@mantine/core';
import { Link, useParams } from 'react-router-dom';
import { ActionButton as Button } from '@components/button/ActionButton';
import { PageLoading } from '@components/loadingOverlay/PageLoading';
import { CatalogFrame } from '../publicLibrary/CatalogFrame';
import { PublicCatalog } from '../publicLibrary/PublicCatalog';
import { message } from '../experiments/api';
import { getUser, type PublicUser } from './api';

export function PublicProfile() {
  const { userId = '' } = useParams();
  const [user, setUser] = useState<PublicUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    setUser(null);
    setError(null);
    void getUser(userId, abort.signal)
      .then((next) => {
        if (!abort.signal.aborted) setUser(next);
      })
      .catch((cause: unknown) => {
        if (!abort.signal.aborted) setError(message(cause));
      });
    return () => abort.abort();
  }, [userId, retry]);
  return (
    <CatalogFrame>
      <Anchor component={Link} to="/catalog?kind=users">
        Browse people
      </Anchor>
      {error ? (
        <Alert color="red" title="Profile unavailable" role="alert">
          <Text>{error}</Text>
          <Button
            variant="subtle"
            onClick={() => setRetry((value) => value + 1)}
          >
            Try again
          </Button>
        </Alert>
      ) : !user || user.id !== userId ? (
        <PageLoading message="Loading profile…" />
      ) : (
        <>
          <Group>
            <Avatar name={user.display_name} color="initials" size="lg" />
            <div>
              <Title order={1}>{user.display_name}</Title>
              <Text c="dimmed">{user.school || 'Independent member'}</Text>
            </div>
          </Group>
          <Text c="dimmed">
            Public configurations and runs. Find tunes on each CVT’s page.
          </Text>
          <PublicCatalog key={user.id} authorId={user.id} />
        </>
      )}
    </CatalogFrame>
  );
}
