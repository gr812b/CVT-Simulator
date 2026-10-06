import { useState } from 'react';
import { ActionIcon, Popover, Text } from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';

/** Click/touch and keyboard accessible; never requires a hover gesture. */
export function PlotInfo({ title, description }: { title: string; description: string }) {
  const [opened, setOpened] = useState(false);
  return <Popover opened={opened} onChange={setOpened} width={340} position="bottom-start" withArrow trapFocus>
    <Popover.Target>
      <ActionIcon variant="subtle" color="gray" size="sm" aria-label={`About ${title}`} aria-expanded={opened}
        onClick={() => setOpened(o => !o)}><IconInfoCircle size={17}/></ActionIcon>
    </Popover.Target>
    <Popover.Dropdown style={{ maxWidth: 'calc(100vw - 32px)' }}>
      <Text fw={600} size="sm" mb={5}>{title}</Text>
      <Text size="sm">{description}</Text>
    </Popover.Dropdown>
  </Popover>;
}
