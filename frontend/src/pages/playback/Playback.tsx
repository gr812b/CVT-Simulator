import { useEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Anchor,
  Container,
  Group,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { getSimulationResult, type CompletedSimulationRun } from '@api/client';
import { ActionButton as Button } from '@components/button/ActionButton';
import { PageLoading } from '@components/loadingOverlay/PageLoading';
import { inspectRun, type RunInspection } from '../../features/results/api';
import { RunStatusBadge } from '../../features/results/RunStatusBadge';
import { AuthorLink } from '../../features/community/AuthorLink';
import { useRunActivity } from '../../features/experiments/RunActivity';
import { isActive, message } from '../../features/experiments/api';
import { SimulationPlayback } from './SimulationPlayback';

/** Both public and workspace URLs enter exactly the same result-loading path. */
export function Playback() {
  const { runId } = useParams();
  const [params] = useSearchParams();
  const id = runId ?? params.get('run');
  const [data, setData] = useState<{
    result: CompletedSimulationRun;
    inspection: RunInspection;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const { activity, dismiss } = useRunActivity();
  const reading = useRef(new Set<string>());
  useEffect(() => {
    for (const notice of activity?.unread ?? []) {
      if (notice.run.id !== id || reading.current.has(notice.id)) continue;
      reading.current.add(notice.id);
      void dismiss(notice.id).catch(() => reading.current.delete(notice.id));
    }
  }, [activity, dismiss, id]);
  useEffect(() => {
    let active = true;
    setData(null);
    setError(null);
    if (!id) {
      setError('Choose a run to open its playback.');
      return;
    }
    void inspectRun(id)
      .then(async (inspection) => {
        if (isActive(inspection.run))
          throw new Error(
            'This run is still active. Open playback once it has stopped.',
          );
        const result = await getSimulationResult(id);
        if (active) setData({ result, inspection });
      })
      .catch((cause) => {
        if (active) setError(message(cause));
      });
    return () => {
      active = false;
    };
  }, [id, retry]);
  if (error)
    return (
      <Container py="xl">
        <Alert color="red" title="Playback unavailable">
          {error}
          <Group mt="md">
            <Button onClick={() => setRetry((x) => x + 1)}>Try again</Button>
            <Button
              component={Link}
              to={id ? `/runs/${id}` : '/catalog?kind=runs'}
              variant="default"
            >
              View runs
            </Button>
          </Group>
        </Alert>
      </Container>
    );
  if (!data) return <PageLoading message="Loading result playback…" />;
  const { result, inspection } = data;
  return (
    <>
      <Container fluid py="md">
        <Stack gap="xs">
          <Group justify="space-between">
            <Title order={1}>{inspection.run.name}</Title>
            <RunStatusBadge status={inspection.run.status} />
          </Group>
          <Text size="sm">
            By{' '}
            <AuthorLink
              name={inspection.run.author}
              id={inspection.run.author_id}
            />
          </Text>
          <Group gap="md">
            {inspection.references
              .filter((ref) => ref.href)
              .map((ref) => (
                <Anchor
                  key={ref.kind}
                  component={Link}
                  to={ref.href!}
                  size="sm"
                >
                  {ref.name}
                  {ref.unsaved ? ' · modified for this run' : ''}
                </Anchor>
              ))}
          </Group>
        </Stack>
      </Container>
      <SimulationPlayback
        forceSource={inspection.run.id}
        result={result.result}
        document={result.inputDocumentSnapshot}
        sceneGeometry={result.sceneGeometry}
        course={result.course}
        live={isActive(inspection.run)}
        navigation={[
          { label: 'Run details', to: `/runs/${inspection.run.id}` },
        ]}
      />
    </>
  );
}
