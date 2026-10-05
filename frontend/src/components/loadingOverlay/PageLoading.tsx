import { Center, Loader, Overlay, Portal, Stack, Text } from '@mantine/core';

/** A route transition blocks the entire frame, including its navigation. */
export function PageLoading({ message = 'Loading…' }: { message?: string }) {
  return (
    <Portal>
      <Overlay
        fixed
        zIndex={1000}
        color="var(--mantine-color-body)"
        backgroundOpacity={0.92}
        blur={2}
      >
        <Center h="100dvh">
          <Stack align="center" role="status" aria-live="polite">
            <Loader />
            <Text>{message}</Text>
          </Stack>
        </Center>
      </Overlay>
    </Portal>
  );
}
