import { useEffect, useState } from 'react';
import {
  Alert,
  Anchor,
  Container,
  Group,
  Loader,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { Link } from 'react-router-dom';
import { IconArrowRight, IconPlayerPlay } from '@tabler/icons-react';
import { useAuth } from '@contexts/AuthContext';
import { useRunActivity } from '../../features/experiments/RunActivity';
import {
  listRuns,
  message,
  type RunStatus,
} from '../../features/experiments/api';
import { RunStatusBadge } from '../../features/results/RunStatusBadge';

const guide = [
  {
    title: 'Choose your hardware',
    text: 'Pick a vehicle, CVT, belt and engine. Use the McMaster defaults or save your own parts in the physical library.',
    to: '/library',
    link: 'Manage your parts',
  },
  {
    title: 'Choose a tune and a road',
    text: 'Build a run walks you through the setup. Pick an existing tune and load case, or create one when you need it.',
    to: '/input',
    link: 'Build a run',
  },
  {
    title: 'Inspect the result',
    text: 'Replay the motion, check forces and belt slip, or export the data. Start another run from the same setup to try a different tune.',
    to: '/runs',
    link: 'See your runs',
  },
];

export function Dashboard() {
  const { session } = useAuth();
  const { activity } = useRunActivity();
  const [recent, setRecent] = useState<RunStatus[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const active = activity?.active;
  const latestNotice = activity?.unread[0]?.id;
  useEffect(() => {
    const abort = new AbortController();
    setError(null);
    setBusy(true);
    void listRuns(abort.signal, 4)
      .then((runs) => {
        if (!abort.signal.aborted) setRecent(runs);
      })
      .catch((cause) => {
        if (!abort.signal.aborted) setError(message(cause));
      })
      .finally(() => {
        if (!abort.signal.aborted) setBusy(false);
      });
    return () => abort.abort();
  }, [active?.id, active?.status, latestNotice, retry]);
  const runs = active
    ? [active, ...recent.filter((run) => run.id !== active.id)].slice(0, 4)
    : recent;
  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <Group justify="space-between" align="start">
          <div>
            <Title order={1}>Welcome, {session?.user.display_name}.</Title>
            <Text c="dimmed" mt="sm">
              Set up a simulation or pick up where you left off.
            </Text>
          </div>
          <Button
            component={Link}
            to="/input"
            rightSection={<IconArrowRight size={18} />}
          >
            Build a run
          </Button>
        </Group>
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
          <Paper withBorder p="lg">
            <Stack>
              <Group justify="space-between">
                <Title order={2} size="h3">
                  Your recent runs
                </Title>
                <Anchor component={Link} to="/runs" size="sm">
                  View all
                </Anchor>
              </Group>
              {busy && <Loader size="sm" aria-label="Loading recent runs" />}
              {error && (
                <Alert color="red" title="Couldn’t load recent runs">
                  {error}
                  <Button
                    variant="subtle"
                    size="xs"
                    onClick={() => setRetry((value) => value + 1)}
                  >
                    Try again
                  </Button>
                </Alert>
              )}
              {runs.map((run) => (
                <Paper key={run.id} withBorder p="sm">
                  <Group wrap="nowrap" justify="space-between">
                    <Stack gap={3} miw={0}>
                      <Anchor
                        component={Link}
                        to={`/runs/${run.id}`}
                        fw={600}
                        truncate
                      >
                        {run.name ?? 'Simulation'}
                      </Anchor>
                      <Text c="dimmed" size="xs">
                        {new Date(run.submitted_at).toLocaleString()}
                      </Text>
                      {run.status === 'queued' &&
                        run.queue_position != null && (
                          <Text size="xs">
                            Queue position: {run.queue_position}
                          </Text>
                        )}
                    </Stack>
                    <RunStatusBadge status={run.status} />
                  </Group>
                </Paper>
              ))}
              {!busy && !error && !runs.length && (
                <Text c="dimmed">
                  Your simulations will appear here. Start with the demo to see
                  what a result looks like, or build your first run.
                </Text>
              )}
            </Stack>
          </Paper>
          <Paper withBorder p="lg">
            <Stack h="100%" justify="space-between">
              <Stack gap="sm">
                <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                  Try a completed run
                </Text>
                <Title order={2} size="h3">
                  McMaster CVT on the hill course
                </Title>
                <Text c="dimmed">
                  Follow a launch, a 45° climb, a descent and a second climb.
                  Scrub through the run to see the ratio change and inspect the
                  pulley forces alongside the plots.
                </Text>
              </Stack>
              <Button
                component={Link}
                to="/demo"
                variant="light"
                leftSection={<IconPlayerPlay size={18} />}
                mt="md"
                style={{ alignSelf: 'start' }}
              >
                Open the demo
              </Button>
            </Stack>
          </Paper>
        </SimpleGrid>
        <section aria-labelledby="setup-guide-title">
          <Title id="setup-guide-title" order={2} size="h3" mb="lg">
            From a setup to a result
          </Title>
          <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg">
            {guide.map((step, index) => (
              <Stack key={step.title} gap="sm">
                <Text size="sm" c="red" fw={600}>
                  0{index + 1}
                </Text>
                <Title order={3} size="h4">
                  {step.title}
                </Title>
                <Text size="sm" c="dimmed">
                  {step.text}
                </Text>
                <Anchor component={Link} to={step.to} size="sm">
                  {step.link} →
                </Anchor>
              </Stack>
            ))}
          </SimpleGrid>
        </section>
        <Text size="sm" c="dimmed">
          Looking for a starting point? Browse other setups in the{' '}
          <Anchor component={Link} to="/catalog" size="sm">
            public library
          </Anchor>
          , or check belt fit and ratio range in the{' '}
          <Anchor component={Link} to="/geometry" size="sm">
            geometry study
          </Anchor>
          .
        </Text>
      </Stack>
    </Container>
  );
}
