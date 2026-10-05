import { Tabs } from '@mantine/core';
import { kindLabels } from './api';
export function LibraryTabs({
  value,
  onChange,
  runs = false,
  people = false,
}: {
  value: string;
  onChange: (value: string | null) => void;
  runs?: boolean;
  people?: boolean;
}) {
  return (
    <Tabs value={value} onChange={onChange}>
      <Tabs.List>
        {Object.entries(kindLabels).map(([key, label]) => (
          <Tabs.Tab value={key} key={key}>
            {label}
          </Tabs.Tab>
        ))}
        <Tabs.Tab
          value="load-cases"
          ml="md"
          style={{
            borderInlineStart: '1px solid var(--mantine-color-default-border)',
          }}
        >
          Load cases
        </Tabs.Tab>
        {runs && <Tabs.Tab value="runs">Runs</Tabs.Tab>}
        {people && <Tabs.Tab value="users">People</Tabs.Tab>}
      </Tabs.List>
    </Tabs>
  );
}
