import { AuthorLink } from '../community/AuthorLink';
import type { ReactNode } from 'react';
import { Badge, Group, Paper, Stack, Text, Title } from '@mantine/core';

/** Shared presentation for saved physical items, load cases and public entries. */
export function LibraryCard({
  name,
  description,
  author,
  authorId,
  badge,
  children,
  actions,
}: {
  name: string;
  description?: string;
  author: string;
  authorId?: string | null;
  badge: string;
  children?: ReactNode;
  actions: ReactNode;
}) {
  return (
    <Paper withBorder p="lg" radius="lg" h="100%">
      <Stack h="100%" justify="space-between">
        <Stack gap="sm">
          <Group>
            <Badge variant="outline">{badge}</Badge>
          </Group>
          <Title order={3} size="h4" style={{ overflowWrap: 'anywhere' }}>
            {name}
          </Title>
          <Text size="sm" c="dimmed" lineClamp={3}>
            {description || 'A saved configuration ready to use in a run.'}
          </Text>
          <Text size="sm">
            By <AuthorLink name={author} id={authorId} />
          </Text>
          {children}
        </Stack>
        <Stack gap="xs" mt="sm">
          {actions}
        </Stack>
      </Stack>
    </Paper>
  );
}
