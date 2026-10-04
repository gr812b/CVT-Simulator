import { Brand } from '@components/appShell/Brand';
import { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Container,
  Group,
  Loader,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { getDemoPlayback, type DemoPlayback } from '@api/client';
import { SimulationPlayback } from '@pages/playback/SimulationPlayback';

/** A shipped, completed result. Opening this page never queues a simulation. */
export function Demo() {
  const [demo, setDemo] = useState<DemoPlayback | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    void getDemoPlayback(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setDemo(value);
      })
      .catch((cause) => {
        if (!controller.signal.aborted)
          setError(cause instanceof Error ? cause.message : String(cause));
      });
    return () => controller.abort();
  }, [retry]);
  return (
    <>
      <Container fluid py="lg">
        <Stack gap="sm">
          <Brand />
          <Group>
            <Title order={1}>{demo?.name ?? 'Baja launch demo'}</Title>
            <Badge variant="light">Recorded demo · no account needed</Badge>
          </Group>
          <Text>
            {demo?.description ??
              'Explore the default launch in the same playback used for your own simulations.'}
          </Text>
          <Text size="sm" c="dimmed">
            Play, pause, scrub through the run and download its data. This saved
            example loads without starting a new simulation.
          </Text>
          {error ? (
            <Alert title="Demo unavailable" color="red" role="alert">
              {error}
              <Button
                variant="subtle"
                onClick={() => setRetry((value) => value + 1)}
              >
                Try again
              </Button>
            </Alert>
          ) : (
            !demo && <Loader aria-label="Loading recorded demo" />
          )}
        </Stack>
      </Container>
      {demo && (
        <SimulationPlayback
          result={demo.result}
          document={demo.inputDocumentSnapshot}
          navigation={[
            { label: 'Home', to: '/' },
            { label: 'Public library', to: '/catalog' },
          ]}
        />
      )}
    </>
  );
}
