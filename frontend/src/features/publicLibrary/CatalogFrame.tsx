import type { ReactNode } from 'react';
import { Button, Container, Group, Stack, Text } from '@mantine/core';
import { Link } from 'react-router-dom';
import { useAuth } from '@contexts/AuthContext';

export function CatalogFrame({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  return (
    <Container size="xl" py="lg">
      <Stack gap="xl">
        <Group justify="space-between">
          <Text
            component={Link}
            to="/catalog"
            c="red.4"
            fw={900}
            size="xl"
            td="none"
          >
            CINDER · Public library
          </Text>
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
