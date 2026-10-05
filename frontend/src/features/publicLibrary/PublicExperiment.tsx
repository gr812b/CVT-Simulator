import { AuthorLink } from '../community/AuthorLink';
import { LoadCaseEditor } from '../experiments/LoadCaseEditor';
import { useEffect, useState } from 'react';
import {
  Accordion,
  Anchor,
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
  restoreExperiment,
  message,
  type ExperimentDetail,
} from '../experiments/api';
import { RoadPreview } from '../experiments/RoadPreview';
import { CatalogFrame } from './CatalogFrame';
import { ConfigurationBack } from '../physicalLibrary/ConfigurationLink';
import { TuneDetails } from '../experiments/TuneDetails';
import { useNavigate, useLocation } from 'react-router-dom';

export function PublicExperiment() {
  const { objectId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const revision = params.get('revision') ?? undefined;
  const [editing, setEditing] = useState(false);
  const { session } = useAuth();
  const [detail, setDetail] = useState<ExperimentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [working, setWorking] = useState(false);
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
      <ConfigurationBack
        to={`/catalog?kind=${detail?.item.kind === 'tunes' ? 'cvts' : 'load-cases'}`}
        label="public library"
      />
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
            {detail.item.archived && <Badge color="gray">Archived</Badge>}
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
              state={location.state}
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
            <TuneDetails
              detail={detail}
              historical={Boolean(revision)}
              onSaved={(next) => {
                setDetail(next);
                navigate(`/catalog/tunes/${next.item.id}`, {
                  state: location.state,
                });
              }}
            />
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
                    <Group justify="space-between" key={item.id}>
                      <Anchor
                        component={Link}
                        to={`/catalog/${detail.item.kind === 'tunes' ? 'tunes' : 'load-cases'}/${detail.item.id}?revision=${item.id}`}
                        state={location.state}
                      >
                        Version {item.number} ·{' '}
                        {new Date(item.created_at).toLocaleDateString()}
                        {item.change_note ? ` · ${item.change_note}` : ''}
                      </Anchor>
                      {detail.item.owned &&
                        !revision &&
                        !detail.item.archived &&
                        item.id !== detail.item.revision_id && (
                          <Button
                            size="xs"
                            variant="subtle"
                            disabled={working}
                            onClick={() => {
                              setWorking(true);
                              setError(null);
                              void restoreExperiment(detail, item.id)
                                .then(setDetail)
                                .catch((cause) => setError(message(cause)))
                                .finally(() => setWorking(false));
                            }}
                          >
                            Restore as new version
                          </Button>
                        )}
                    </Group>
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
