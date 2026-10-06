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
import { RunOutcomeNotice } from '../../features/results/RunOutcomeNotice';
import { describeRunOutcome } from '../../features/results/runOutcome';
import { AuthorLink } from '../../features/community/AuthorLink';
import { useRunActivity } from '../../features/experiments/RunActivity';
import { isActive, message } from '../../features/experiments/api';
import { SimulationPlayback } from './SimulationPlayback';

/** Both public and workspace URLs enter exactly the same result-loading path. */
export function Playback() {
  const { runId } = useParams();
  const [params] = useSearchParams();
  const id = runId ?? params.get('run');
  const [result, setResult] = useState<CompletedSimulationRun | null>(null);
  const [inspection, setInspection] = useState<RunInspection | null>(null);
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
    setResult(null);
    setInspection(null);
    setError(null);
    if (!id) {
      setError('Choose a run to open its playback.');
      return;
    }
    void inspectRun(id)
      .then(async (inspection) => {
        if (!active) return;
        setInspection(inspection);
        if (isActive(inspection.run) || !inspection.availability.full_result)
          return;
        const result = await getSimulationResult(id);
        if (active) setResult(result);
      })
      .catch((cause) => {
        if (active) setError(message(cause));
      });
    return () => {
      active = false;
    };
  }, [id, retry]);
  if (error && !inspection)
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
  if (!inspection) return <PageLoading message="Loading result playback…" />;
  const outcome = describeRunOutcome(inspection.run, inspection);
  const unavailable = isActive(inspection.run) || !inspection.availability.full_result;
  return (
    <>
      <Container fluid py="md">
        <Stack gap="xs">
          <Group justify="space-between">
            <Title order={1}>{inspection.run.name}</Title>
            <RunStatusBadge run={inspection.run} outcome={outcome} />
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
          {!result && (
            <RunOutcomeNotice outcome={outcome} availability={inspection.availability} />
          )}
          {outcome.category === 'success' && !inspection.availability.full_result && (
            <Alert color="yellow" title="Full result unavailable" role="alert">
              {inspection.availability.preview
                ? 'A saved preview is available in the run details. Full playback and report exports are unavailable.'
                : 'The full result is no longer available. Its summary and frozen inputs remain in the run details.'}
            </Alert>
          )}
          {error && (
            <Alert color="red" title="Playback could not be loaded" role="alert">
              {error}
              <Button mt="sm" onClick={() => setRetry((value) => value + 1)}>
                Try again
              </Button>
            </Alert>
          )}
          {!result && (
            <Button component={Link} to={`/runs/${inspection.run.id}`} variant="default" w="fit-content">
              View run details
            </Button>
          )}
        </Stack>
      </Container>
      {!result && !error && !unavailable && <PageLoading message="Loading saved trajectory…" />}
      {result && <SimulationPlayback
        forceSource={inspection.run.id}
        result={result.result}
        document={result.inputDocumentSnapshot}
        sceneGeometry={result.sceneGeometry}
        course={result.course}
        live={isActive(inspection.run)}
        outcome={outcome}
        navigation={[
          { label: 'Run details', to: `/runs/${inspection.run.id}` },
        ]}
      />}
    </>
  );
}
