import { PublicHeader } from '@components/appShell/PublicHeader';
import layout from '@components/appShell/PageGutter.module.scss';
import { useEffect, useState } from 'react';
import {
  Alert,
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
      <Container fluid py="lg" className={layout.gutter}>
        <Stack gap="sm">
          <PublicHeader />
          <Group>
            <Title order={1}>{demo?.name ?? 'Demo course'}</Title>
          </Group>
          <Text>
            {demo?.description ??
              'Explore acceleration, 45° and 30° climbs with a descent between them in the same playback used for your own simulations.'}
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
          forceSource="demo"
          result={demo.result}
          document={demo.inputDocumentSnapshot}
          sceneGeometry={demo.scene_geometry}
          course={demo.course}
          navigation={[{ label: 'Home', to: '/' }]}
        />
      )}
    </>
  );
}
