import { useState, type ReactNode } from 'react';
import { Collapse, Group, Paper, Stack, Text } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';

/** Keep the common selection path small; mount advanced fields only when requested. */
export function EditorDisclosure({
  title, summary, initiallyOpen = false, children,
}: {
  title: string;
  summary?: ReactNode;
  initiallyOpen?: boolean;
  children: ReactNode;
}) {
  const [opened, setOpened] = useState(initiallyOpen);
  return (
    <Paper withBorder p="md">
      <Stack gap="sm">
        <Group justify="space-between" align="start">
          <div>
            <Text fw={600}>{title}</Text>
            {summary && <Text size="sm" c="dimmed">{summary}</Text>}
          </div>
          <Button
            variant="light" size="sm" aria-expanded={opened}
            onClick={() => setOpened(x => !x)}
          >
            {opened ? 'Close editor' : `Edit ${title.toLowerCase()}`}
          </Button>
        </Group>
        <Collapse expanded={opened}>{opened && children}</Collapse>
      </Stack>
    </Paper>
  );
}
