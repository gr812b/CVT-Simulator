import type { ReactNode } from 'react';
import { Container, Stack } from '@mantine/core';

export function CatalogFrame({ children }: { children: ReactNode }) {
  return (
    <Container size="xl" py="lg">
      <Stack gap="xl">{children}</Stack>
    </Container>
  );
}
