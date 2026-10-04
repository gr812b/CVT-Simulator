import { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Code,
  Group,
  Loader,
  Paper,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { Link, useParams } from 'react-router-dom';
import { ActionButton as Button } from '@components/button/ActionButton';
import { useAuth } from '@contexts/AuthContext';
import {
  getExperiment,
  listExperiments,
  message,
  type ExperimentDetail,
  type ExperimentItem,
} from '../experiments/api';
import { RoadPreview } from '../experiments/RoadPreview';
import { CatalogFrame } from './CatalogFrame';

export function PublicTuneList() {
  const [items, setItems] = useState<ExperimentItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let stopped = false;
    void listExperiments('tunes')
      .then((next) => {
        if (!stopped) setItems(next.filter((x) => !x.archived));
      })
      .catch((cause) => {
        if (!stopped) setError(message(cause));
      });
    return () => {
      stopped = true;
    };
  }, []);
  return (
    <Stack>
      <Title order={2}>Tunes</Title>
      <Text c="dimmed">
        Saved tuning values with their pinned vehicle setup.
      </Text>
      {error && <Alert color="red">{error}</Alert>}
      {!items && !error && <Loader />}
      {items?.map((item) => (
        <Paper withBorder p="lg" key={item.id}>
          <Group justify="space-between">
            <div>
              <Text fw={600}>{item.name}</Text>
              <Text size="sm" c="dimmed">
                Revision {item.revision_number} · {item.description}
              </Text>
            </div>
            <Button
              component={Link}
              to={`/catalog/tunes/${item.id}`}
              variant="light"
            >
              View tune
            </Button>
          </Group>
        </Paper>
      ))}
      {items?.length === 0 && <Text>No saved tunes yet.</Text>}
    </Stack>
  );
}

export function PublicExperiment() {
  const { objectId } = useParams();
  const { session } = useAuth();
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let stopped = false;
    setDetail(null);
    setError(null);
    void getExperiment(objectId ?? '')
      .then((next) => {
        if (!stopped) setDetail(next);
      })
      .catch((cause) => {
        if (!stopped) setError(message(cause));
      });
    return () => {
      stopped = true;
    };
  }, [objectId, retry]);
  return (
    <CatalogFrame>
      <Button
        component={Link}
        to={`/catalog?kind=${detail?.item.kind === 'tunes' ? 'tunes' : 'load-cases'}`}
        variant="subtle"
        w="fit-content"
      >
        Back to public library
      </Button>
      {error && (
        <Alert color="red">
          {error}
          <Button variant="subtle" onClick={() => setRetry((x) => x + 1)}>
            Try again
          </Button>
        </Alert>
      )}
      {!detail ? (
        !error && <Loader />
      ) : (
        <>
          <Group>
            <Title order={1}>{detail.document.name}</Title>
            <Badge>Public · revision {detail.item.revision_number}</Badge>
          </Group>
          <Text style={{ whiteSpace: 'pre-wrap' }}>
            {detail.document.notes}
          </Text>
          {detail.document.kind === 'scenarios' ? (
            <>
              <Paper withBorder p="lg">
                <RoadPreview road={detail.document.road} />
              </Paper>
              <Text>
                {detail.document.duration_s} s default duration · initial
                primary speed{' '}
                {(
                  ((detail.document.initial?.primary_angular_speed_rad_per_s ??
                    0) *
                    30) /
                  Math.PI
                ).toFixed(0)}{' '}
                RPM.
              </Text>
              <Button
                component={Link}
                to={
                  session
                    ? `/input?scenario=${detail.item.id}`
                    : `/login?next=${encodeURIComponent(`/input?scenario=${detail.item.id}`)}`
                }
              >
                Use this load case
              </Button>
            </>
          ) : (
            <Button
              component={Link}
              to={
                session
                  ? `/input?setup=${detail.item.setup_object_id}&tune=${detail.item.id}`
                  : `/login?next=${encodeURIComponent(`/input?setup=${detail.item.setup_object_id}&tune=${detail.item.id}`)}`
              }
            >
              Use this tune
            </Button>
          )}
          <Title order={2} size="h3">
            Saved values
          </Title>
          <Code block>{JSON.stringify(detail.document, null, 2)}</Code>
          <Text size="sm" c="dimmed">
            Public content can be inspected without an account. Sign in to make
            your own copy or submit a simulation.
          </Text>
        </>
      )}
    </CatalogFrame>
  );
}
