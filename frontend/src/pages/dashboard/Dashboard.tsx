import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Container,
  Group,
  Loader,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { Link } from 'react-router-dom';
import {
  IconArrowRight,
  IconGeometry,
  IconPlayerPlay,
} from '@tabler/icons-react';
import { useAuth } from '@contexts/AuthContext';
import { useLoading } from '@contexts/LoadingContext';
import { useRunSimulation } from '@hooks/useRunSimulation';
import { useRunActivity } from '../../features/experiments/RunActivity';
import {
  buildRunSetupForVehicle,
  getDefaultRunSetup,
  type DefaultRunSetup,
} from '@api/client';

export function Dashboard() {
  const { session } = useAuth();
  const { isLoading, loadingMessage } = useLoading();
  const { runLibrarySetup } = useRunSimulation();
  const { activity } = useRunActivity();
  const [setup, setSetup] = useState<DefaultRunSetup | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setSetup(await getDefaultRunSetup());
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to load your workspace.',
      );
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const selectVehicle = async (id: string | null) => {
    if (!setup || !id) return;
    setBusy(true);
    setError(null);
    try {
      setSetup(await buildRunSetupForVehicle(setup.vehicleAssemblies, id));
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to load this vehicle.',
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <div>
          <Badge variant="light" mb="sm">
            Your workspace
          </Badge>
          <Title order={1}>Welcome, {session?.user.display_name}.</Title>
          <Text c="dimmed" mt="sm">
            A place to configure your drivetrain, explore its geometry, and
            understand how it performs.
          </Text>
        </div>
        <Paper withBorder p="lg">
          <Group justify="space-between">
            <div>
              <Title order={2} size="h3">
                Your physical library
              </Title>
              <Text size="sm" c="dimmed">
                Create a vehicle setup, reuse engines and belts, and keep a
                history of every saved change.
              </Text>
            </div>
            <Button component={Link} to="/library/setups">
              Open library
            </Button>
          </Group>
        </Paper>
        <Paper withBorder p="lg">
          <Group justify="space-between">
            <div>
              <Title order={2} size="h3">
                Runs & public configurations
              </Title>
              <Text size="sm" c="dimmed">
                Find past results or copy a published setup to begin your next
                experiment.
              </Text>
            </div>
            <Group>
              <Button component={Link} to="/runs" variant="light">
                Run history
              </Button>
              <Button component={Link} to="/catalog" variant="default">
                Public library
              </Button>
            </Group>
          </Group>
        </Paper>
        <Paper withBorder p="xl" radius="lg">
          <Stack>
            <Group justify="space-between">
              <Title order={2} size="h3">
                Start with a vehicle baseline
              </Title>
              {busy && <Loader size="sm" aria-label="Loading baselines" />}
            </Group>
            <Text size="sm" c="dimmed">
              Choose a released setup from your workspace or the sample catalog.
              Runs are saved to your account.
            </Text>
            {error && (
              <Alert color="yellow" role="alert" title="Baseline unavailable">
                {error}
                <Button
                  variant="subtle"
                  size="xs"
                  onClick={() => void load()}
                  ml="sm"
                >
                  Try again
                </Button>
              </Alert>
            )}
            {setup && (
              <>
                <Select
                  label="Vehicle setup"
                  value={setup.selectedVehicleAssembly.id}
                  data={setup.vehicleAssemblies.map((item) => ({
                    value: item.id,
                    label: item.name,
                  }))}
                  onChange={(id) => void selectVehicle(id)}
                  disabled={busy || isLoading}
                  allowDeselect={false}
                />
                <Group gap="xs">
                  <Badge variant="outline" color="gray">
                    {setup.selectedLoadCase?.name ?? 'No load case'}
                  </Badge>
                  <Badge variant="outline" color="gray">
                    {setup.selectedTune?.name ?? 'Baseline tuning'}
                  </Badge>
                </Group>
                <Group mt="sm">
                  <Button
                    leftSection={<IconPlayerPlay size={18} />}
                    loading={isLoading}
                    disabledReason={
                      activity?.active
                        ? 'You already have a queued or running simulation. Wait for it to finish or cancel it first.'
                        : busy
                          ? 'Wait for the selected baseline to load.'
                          : !setup.selectedLoadCase ||
                              !setup.selectedExecutionPreset
                            ? 'Choose a baseline with a load case and execution preset.'
                            : undefined
                    }
                    onClick={() => void runLibrarySetup(setup.selection)}
                  >
                    Run simulation
                  </Button>
                  <Button
                    component={Link}
                    to="/input"
                    variant="default"
                    rightSection={<IconArrowRight size={18} />}
                  >
                    Build a run
                  </Button>
                </Group>
              </>
            )}
            {isLoading && (
              <Text role="status" size="sm" c="dimmed">
                {loadingMessage}
              </Text>
            )}
          </Stack>
        </Paper>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Paper withBorder p="xl">
            <Stack>
              <IconGeometry size={28} color="var(--mantine-color-red-4)" />
              <Title order={2} size="h3">
                Explore geometry
              </Title>
              <Text size="sm" c="dimmed">
                Explore belt dimensions, pulley radii and the available CVT
                ratio range.
              </Text>
              <Button component={Link} to="/geometry" variant="light">
                Open geometry study
              </Button>
            </Stack>
          </Paper>
          <Paper withBorder p="xl">
            <Stack>
              <Title order={2} size="h3">
                Reusable load cases
              </Title>
              <Text size="sm" c="dimmed">
                Pick a flat road, climb, descent or custom route for any
                vehicle.
              </Text>
              <Button component={Link} to="/load-cases" variant="light">
                Open load cases
              </Button>
            </Stack>
          </Paper>
        </SimpleGrid>
      </Stack>
    </Container>
  );
}
