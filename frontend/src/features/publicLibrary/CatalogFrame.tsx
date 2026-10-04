import { Brand } from '@components/appShell/Brand';
import type { ReactNode } from 'react';
import { Container, Group, Stack } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { Link } from 'react-router-dom';
import { useAuth } from '@contexts/AuthContext';

export function CatalogFrame({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  return (
    <Container size="xl" py="lg">
      <Stack gap="xl">
        <Group justify="space-between">
          <Brand />
          <Button
            component={Link}
            to={session ? '/dashboard' : '/login'}
            variant="default"
          >
            {session ? 'My workspace' : 'Sign in'}
          </Button>
        </Group>
        {children}
      </Stack>
    </Container>
  );
}
