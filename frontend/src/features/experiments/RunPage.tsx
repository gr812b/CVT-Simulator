import { PageLoading } from '@components/loadingOverlay/PageLoading';
import { RunStatusBadge } from '../results/RunStatusBadge';
import { AuthorLink } from '../community/AuthorLink';
import { useAuth } from '@contexts/AuthContext';
import { useEffect, useRef, useState } from 'react';
import {
  Accordion,
  Alert,
  Code,
  Container,
  Group,
  Paper,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { cancelRun, isActive, message, rerun, type RunStatus } from './api';
import { useRunActivity } from './RunActivity';
import { inspectRun, renameRun, type RunInspection } from '../results/api';
import { ResultDetails } from '../results/ResultDetails';
import { RunOutcomeNotice } from '../results/RunOutcomeNotice';
import { describeRunOutcome } from '../results/runOutcome';

export function RunPage() {
  const { runId } = useParams();
  const { session } = useAuth();
  const navigate = useNavigate();
  const { refresh, activity, dismiss } = useRunActivity();
  const readingNotices = useRef(new Set<string>());
  useEffect(() => {
    for (const notice of activity?.unread ?? []) {
      if (notice.run.id !== runId || readingNotices.current.has(notice.id))
        continue;
      readingNotices.current.add(notice.id);
      void dismiss(notice.id).catch(() =>
        readingNotices.current.delete(notice.id),
      );
    }
  }, [runId, activity, dismiss]);
  const [run, setRun] = useState<RunStatus | null>(null);
  const [inspection, setInspection] = useState<RunInspection | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const retryKey = useRef(crypto.randomUUID());
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    setRun(null);
    setInspection(null);
    setEditingName(false);
    setError(null);
    retryKey.current = crypto.randomUUID();
    const poll = async () => {
      if (!runId) return;
      try {
        const detail = await inspectRun(runId);
        const next = detail.run;
        if (!disposed) {
          setRun(next);
          setInspection(detail);
          setError(null);
          if (isActive(next)) timer = setTimeout(poll, 1500);
        }
      } catch (cause) {
        if (!disposed) {
          setError(message(cause));
          timer = setTimeout(poll, 5000);
        }
      }
    };
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [runId]);
  const act = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  };
  const outcome = run ? describeRunOutcome(run, inspection ?? undefined) : null;
  return (
    <Container size="lg" py="lg">
      <Stack>
        <Group justify="space-between">
          <Title order={1}>Simulation run</Title>
          <Button
            component={Link}
            to={session ? '/runs' : '/catalog?kind=runs'}
            variant="default"
          >
            All runs
          </Button>
        </Group>
        {error && (
          <Alert color="red" role="alert">
            {error}
          </Alert>
        )}
        {run?.queue_position && (
          <Alert
            color="violet"
            title={`Position ${run.queue_position} in the queue`}
          >
            Waiting for a worker. This position may change as workers claim
            jobs.
          </Alert>
        )}
        {!run ? (
          !error && <PageLoading message="Loading run…" />
        ) : (
          <>
            <Paper withBorder p="lg">
              <Stack>
                <Group justify="space-between">
                  <Title order={2}>{run.name}</Title>
                  <RunStatusBadge run={run} outcome={outcome ?? undefined} />
                </Group>
                {inspection?.owned &&
                  (editingName ? (
                    <Group align="end">
                      <TextInput
                        label="Run name"
                        value={name}
                        maxLength={240}
                        onChange={(event) => setName(event.currentTarget.value)}
                      />
                      <Button
                        loading={busy}
                        disabledReason={
                          !name.trim() ? 'Enter a run name.' : undefined
                        }
                        onClick={() =>
                          void act(async () => {
                            const next = await renameRun(run.id, {
                              name,
                              expected_name: run.name ?? 'Simulation',
                            });
                            setRun(next);
                            if (inspection)
                              setInspection({ ...inspection, run: next });
                            setEditingName(false);
                          })
                        }
                      >
                        Save name
                      </Button>
                      <Button
                        variant="subtle"
                        onClick={() => setEditingName(false)}
                      >
                        Cancel rename
                      </Button>
                    </Group>
                  ) : (
                    <Button
                      variant="subtle"
                      size="xs"
                      w="fit-content"
                      onClick={() => {
                        setName(run.name ?? 'Simulation');
                        setEditingName(true);
                      }}
                    >
                      Rename run
                    </Button>
                  ))}
                <Text size="sm" c="dimmed">
                  By <AuthorLink name={run.author} id={run.author_id} /> ·
                  Submitted {new Date(run.submitted_at).toLocaleString()} ·
                  CINDER {run.cinder_package_version}
                </Text>
                <Text size="xs" c="dimmed" style={{ overflowWrap: 'anywhere' }}>
                  Run {run.id}
                </Text>
                {isActive(run) && (
                  <Alert
                    color="blue"
                    title={
                      run.cancel_requested_at
                        ? 'Stopping simulation'
                        : run.status === 'queued'
                          ? 'Waiting for a worker'
                          : 'Computing'
                    }
                  >
                    {run.cancel_requested_at
                      ? 'Your slot will be released once the computation has stopped.'
                      : inspection?.owned
                        ? 'You can leave this page. The run continues on the server; Activity will show its result.'
                        : 'This simulation is running. Its latest saved progress appears here.'}
                  </Alert>
                )}
                {outcome && !isActive(run) && (
                  <RunOutcomeNotice
                    outcome={outcome}
                    availability={inspection?.availability}
                    showReference={false}
                  />
                )}
                <Group>
                  {(isActive(run) || inspection?.availability.full_result) && (
                    <Button
                      component={Link}
                      to={`/playback?run=${run.id}`}
                      disabledReason={
                        isActive(run)
                          ? 'Playback is available once this run has stopped.'
                          : undefined
                      }
                    >
                      {outcome?.partial ? 'Open partial playback' : 'Open result playback'}
                    </Button>
                  )}
                  {inspection?.owned &&
                    (isActive(run) ? (
                      <Button
                        variant="light"
                        color="red"
                        loading={busy}
                        disabledReason={
                          run.cancel_requested_at
                            ? 'Cancellation has already been requested.'
                            : undefined
                        }
                        onClick={() =>
                          void act(async () => setRun(await cancelRun(run.id)))
                        }
                      >
                        Cancel run
                      </Button>
                    ) : (
                      <Button
                        variant="light"
                        loading={busy}
                        disabledReason={
                          activity?.active
                            ? 'You already have a queued or running simulation. Wait for it to finish or cancel it from Activity.'
                            : undefined
                        }
                        onClick={() =>
                          void act(async () => {
                            const next = await rerun(run.id, retryKey.current);
                            navigate(`/runs/${next.id}`);
                          })
                        }
                      >
                        Rerun saved inputs
                      </Button>
                    ))}
                  {run.parent_run_id && (
                    <Button
                      component={Link}
                      to={`/runs/${run.parent_run_id}`}
                      variant="subtle"
                    >
                      Original run
                    </Button>
                  )}
                  <Button
                    variant="default"
                    loading={busy}
                    disabledReason={
                      !inspection
                        ? 'Wait for the run details to load.'
                        : (inspection.experiment_unavailable_reason ??
                          undefined)
                    }
                    component={Link}
                    to={
                      session
                        ? `/input?source_run=${run.id}`
                        : `/login?next=${encodeURIComponent(`/input?source_run=${run.id}`)}`
                    }
                  >
                    New experiment from this run
                  </Button>
                </Group>
                <Text size="sm" c="dimmed">
                  {inspection?.experiment_unavailable_reason}
                </Text>
                {inspection?.owned && !isActive(run) && (
                  <Text size="sm" c="dimmed">
                    A rerun creates a new record using these frozen inputs and
                    the currently installed solver. This run will remain
                    unchanged.
                  </Text>
                )}
              </Stack>
            </Paper>
            {inspection && (
              <ResultDetails key={run.id} inspection={inspection} />
            )}
            <Accordion variant="separated">
              <Accordion.Item value="provenance">
                <Accordion.Control>
                  Frozen inputs and solver identity
                </Accordion.Control>
                <Accordion.Panel>
                  <Stack>
                    <Text size="sm">
                      Includes selected revisions, temporary tune values,
                      scenario definition, resolved road and execution controls.
                    </Text>
                    <Code block>
                      {JSON.stringify(
                        {
                          runtime: run.runtime_identity,
                          provenance: run.provenance,
                          contract_hash: run.contract_hash,
                        },
                        null,
                        2,
                      )}
                    </Code>
                  </Stack>
                </Accordion.Panel>
              </Accordion.Item>
            </Accordion>
          </>
        )}
      </Stack>
    </Container>
  );
}
