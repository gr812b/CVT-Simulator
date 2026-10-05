import { AuthorLink } from '../community/AuthorLink';
import { LoadCaseEditor } from '../experiments/LoadCaseEditor';
import { useEffect, useState } from 'react';
import {
  Accordion,
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
import { Link, useParams, useSearchParams } from 'react-router-dom';
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

export function PublicTuneList({ cvtObjectId }: { cvtObjectId: string }) {
  const [items, setItems] = useState<ExperimentItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let stopped = false;
    setItems(null);
    setError(null);
    void listExperiments('tunes', cvtObjectId)
      .then((next) => {
        if (!stopped) setItems(next.filter((x) => !x.archived));
      })
      .catch((cause) => {
        if (!stopped) setError(message(cause));
      });
    return () => {
      stopped = true;
    };
  }, [cvtObjectId]);
  return (
    <Stack>
      <Title order={2}>Tunes for this CVT</Title>
      <Text c="dimmed">
        Saved tunes for this CVT. A tune can be used with any vehicle using its
        CVT version.
      </Text>
      {error && <Alert color="red">{error}</Alert>}
      {!items && !error && <Loader />}
      {items?.map((item) => (
        <Paper withBorder p="lg" key={item.id}>
          <Group justify="space-between">
            <div>
              <Text fw={600}>{item.name}</Text>
              <Text size="sm">
                By <AuthorLink name={item.author} id={item.author_id} />
              </Text>
              <Text size="sm" c="dimmed">
                {item.description}
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
  const [params] = useSearchParams();
  const revision = params.get('revision') ?? undefined;
  const [editing, setEditing] = useState(false);
  const { session } = useAuth();
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let stopped = false;
    setDetail(null);
    setError(null);
    void getExperiment(objectId ?? '', revision)
      .then((next) => {
        if (!stopped) setDetail(next);
      })
      .catch((cause) => {
        if (!stopped) setError(message(cause));
      });
    return () => {
      stopped = true;
    };
  }, [objectId, revision, retry]);
  return (
    <CatalogFrame>
      {editing && (
        <LoadCaseEditor
          id={objectId ?? null}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            setRetry((x) => x + 1);
          }}
        />
      )}
      <Button
        component={Link}
        to={`/catalog?kind=${detail?.item.kind === 'tunes' ? 'cvts' : 'load-cases'}`}
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
            <Badge>Public</Badge>
          </Group>
          <Text size="sm" c="dimmed">
            By{' '}
            <AuthorLink name={detail.item.author} id={detail.item.author_id} />{' '}
            · v{detail.item.revision_number}
          </Text>
          {detail.document.kind === 'scenarios' && session && !revision && (
            <Button
              w="fit-content"
              variant="light"
              onClick={() => setEditing(true)}
            >
              {detail.item.owned ? 'Edit load case' : 'Customize load case'}
            </Button>
          )}
          {revision && (
            <Button
              component={Link}
              to={`/catalog/${detail.document.kind === 'scenarios' ? 'load-cases' : 'tunes'}/${detail.item.id}`}
              variant="light"
              w="fit-content"
            >
              Open latest version
            </Button>
          )}
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
          <Accordion variant="separated">
            <Accordion.Item value="history">
              <Accordion.Control>
                Version history & saved values
              </Accordion.Control>
              <Accordion.Panel>
                <Stack>
                  <Text size="sm">Viewing v{detail.item.revision_number}</Text>
                  {detail.history.map((item) => (
                    <Text size="sm" key={item.id}>
                      Version {item.number} ·{' '}
                      {new Date(item.created_at).toLocaleDateString()}
                      {item.change_note ? ` · ${item.change_note}` : ''}
                    </Text>
                  ))}
                  <Code block>{JSON.stringify(detail.document, null, 2)}</Code>
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
          <Text size="sm" c="dimmed">
            Public content can be inspected without an account. Sign in to make
            your own copy or submit a simulation.
          </Text>
        </>
      )}
    </CatalogFrame>
  );
}
