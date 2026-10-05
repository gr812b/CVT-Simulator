import { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Group,
  Loader,
  Paper,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { Link } from 'react-router-dom';
import { ActionButton as Button } from '@components/button/ActionButton';
import { useAuth } from '@contexts/AuthContext';
import { AuthorLink } from '../community/AuthorLink';
import { ConfigurationLink } from '../physicalLibrary/ConfigurationLink';
import {
  getTuneSurface,
  listExperiments,
  message,
  setDefaultTune,
  type ExperimentItem,
  type TuneSurface,
} from './api';
import { TuneDialog } from './TuneDialog';

export function CvtTunes({
  cvtObjectId,
  cvtRevisionId,
}: {
  cvtObjectId: string;
  cvtRevisionId: string;
}) {
  const { session } = useAuth();
  const [surface, setSurface] = useState<TuneSurface | null>(null);
  const [items, setItems] = useState<ExperimentItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let disposed = false;
    setSurface(null);
    setError(null);
    void Promise.all([
      getTuneSurface(cvtRevisionId),
      listExperiments('tunes', cvtObjectId, { includeArchived: false }),
    ])
      .then(([next, list]) => {
        if (!disposed) {
          setSurface(next);
          setItems(
            list.filter((item) => item.cvt_revision_id === cvtRevisionId),
          );
        }
      })
      .catch((cause) => {
        if (!disposed) setError(message(cause));
      });
    return () => {
      disposed = true;
    };
  }, [cvtObjectId, cvtRevisionId, retry]);
  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Tunes for this CVT</Title>
        {session ? (
          <Button onClick={() => setCreating(true)} disabled={!surface}>
            Add tune
          </Button>
        ) : (
          <Button
            component={Link}
            to={`/login?next=${encodeURIComponent(`/catalog/cvts/${cvtObjectId}?revision=${cvtRevisionId}#tunes`)}`}
          >
            Sign in to add a tune
          </Button>
        )}
      </Group>
      {error && (
        <Alert color="red">
          {error}
          <Button variant="subtle" onClick={() => setRetry((x) => x + 1)}>
            Try again
          </Button>
        </Alert>
      )}
      {!surface && !error && <Loader />}
      {surface &&
        items.map((item) => (
          <Paper key={item.id} withBorder p="md">
            <Group justify="space-between" wrap="wrap">
              <Stack gap={4}>
                <Group gap="xs">
                  <ConfigurationLink
                    to={`/catalog/tunes/${item.id}`}
                    from={surface.cvt_name}
                  >
                    {item.name}
                  </ConfigurationLink>
                  {surface.default_tune.item.id === item.id && (
                    <Badge variant="light">Default</Badge>
                  )}
                </Group>
                <Text size="sm">
                  By <AuthorLink name={item.author} id={item.author_id} />
                </Text>
                {item.description && (
                  <Text size="sm" c="dimmed">
                    {item.description}
                  </Text>
                )}
              </Stack>
              {surface.can_set_default &&
                surface.default_tune.item.id !== item.id && (
                  <Button
                    variant="subtle"
                    size="xs"
                    disabled={busy}
                    onClick={() => {
                      setBusy(true);
                      setError(null);
                      void setDefaultTune(surface, item.id)
                        .then(setSurface)
                        .catch((cause) => setError(message(cause)))
                        .finally(() => setBusy(false));
                    }}
                  >
                    Make default
                  </Button>
                )}
            </Group>
          </Paper>
        ))}
      {creating && surface && (
        <TuneDialog
          mode="new"
          surface={surface}
          onClose={() => setCreating(false)}
          onSaved={() => {
            setCreating(false);
            setRetry((x) => x + 1);
          }}
        />
      )}
    </Stack>
  );
}
