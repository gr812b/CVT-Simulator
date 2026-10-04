import { useEffect, useRef, useState } from 'react';
import {
  Accordion,
  Alert,
  Badge,
  Button,
  Code,
  Container,
  Group,
  Loader,
  Paper,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  cancelRun,
  getRun,
  isActive,
  message,
  rerun,
  type RunStatus,
} from './api';
import { useRunActivity } from './RunActivity';

export function RunPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const { refresh, activity } = useRunActivity();
  const [run, setRun] = useState<RunStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const retryKey = useRef(crypto.randomUUID());
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    setRun(null);
    setError(null);
    retryKey.current = crypto.randomUUID();
    const poll = async () => {
      if (!runId) return;
      try {
        const next = await getRun(runId);
        if (!disposed) {
          setRun(next);
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
  return (
    <Container size="md">
      <Stack>
        <Group justify="space-between">
          <Title order={1}>Simulation run</Title>
          <Button component={Link} to="/input" variant="default">
            New experiment
          </Button>
        </Group>
        {error && (
          <Alert color="red" role="alert">
            {error}
          </Alert>
        )}
        {!run ? (
          <Loader aria-label="Loading run" />
        ) : (
          <>
            <Paper withBorder p="lg">
              <Stack>
                <Group justify="space-between">
                  <Title order={2}>{run.name}</Title>
                  <Badge
                    color={
                      run.status === 'completed'
                        ? 'teal'
                        : isActive(run)
                          ? 'blue'
                          : 'yellow'
                    }
                  >
                    {run.status}
                  </Badge>
                </Group>
                <Text size="sm" c="dimmed">
                  Submitted {new Date(run.submitted_at).toLocaleString()} ·
                  CINDER {run.cinder_package_version}
                </Text>
                <Text size="xs" c="dimmed" style={{ overflowWrap: 'anywhere' }}>
                  Run {run.id}
                </Text>
                {isActive(run) && (
                  <Alert
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
                      : 'You can leave this page or close the browser. The run continues on the server, and its update will be waiting in Activity.'}
                  </Alert>
                )}
                {run.error && (
                  <Alert color="red" title="Run did not complete">
                    {run.error.message}
                  </Alert>
                )}
                <Group>
                  {run.status === 'completed' && (
                    <Button component={Link} to={`/playback?run=${run.id}`}>
                      Open result playback
                    </Button>
                  )}
                  {isActive(run) ? (
                    <Button
                      variant="light"
                      color="red"
                      loading={busy}
                      disabled={Boolean(run.cancel_requested_at)}
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
                      disabled={Boolean(activity?.active)}
                      onClick={() =>
                        void act(async () => {
                          const next = await rerun(run.id, retryKey.current);
                          navigate(`/runs/${next.id}`);
                        })
                      }
                    >
                      Rerun frozen inputs
                    </Button>
                  )}
                  {run.parent_run_id && (
                    <Button
                      component={Link}
                      to={`/runs/${run.parent_run_id}`}
                      variant="subtle"
                    >
                      Original run
                    </Button>
                  )}
                </Group>
                {!isActive(run) && (
                  <Text size="sm" c="dimmed">
                    A rerun creates a new record using these frozen inputs and
                    the currently installed solver. This run will remain
                    unchanged.
                  </Text>
                )}
              </Stack>
            </Paper>
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
