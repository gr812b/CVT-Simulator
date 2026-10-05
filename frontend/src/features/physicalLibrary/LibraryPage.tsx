import { LoadCaseEditor } from '../experiments/LoadCaseEditor';
import { useState } from 'react';
import { Container, Group, Stack, Tabs, Text, Title } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { IconPlus } from '@tabler/icons-react';
import {
  Link,
  Navigate,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom';
import { isPhysicalKind, kindLabels, singularLabels } from './api';
import { LibraryBrowser } from './LibraryBrowser';

export function LibraryPage() {
  const { kind } = useParams();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [newLoadCase, setNewLoadCase] = useState(false);
  const [loadCaseRefresh, setLoadCaseRefresh] = useState(0);
  if (!isPhysicalKind(kind) && kind !== 'load-cases')
    return <Navigate to="/library/setups" replace />;
  return (
    <Container size="xl" py="lg">
      {newLoadCase && (
        <LoadCaseEditor
          id={null}
          onClose={() => setNewLoadCase(false)}
          onSaved={() => {
            setNewLoadCase(false);
            setLoadCaseRefresh((x) => x + 1);
          }}
        />
      )}
      <Stack gap="xl">
        <Group justify="space-between" align="start" mih={78}>
          <div>
            <Title order={1}>Physical library</Title>
            <Text c="dimmed" mt="xs">
              Reusable vehicles, components and load cases for your simulations.
            </Text>
          </div>
          {kind === 'load-cases' && (
            <Button
              leftSection={<IconPlus size={17} />}
              onClick={() => setNewLoadCase(true)}
            >
              New load case
            </Button>
          )}
          {isPhysicalKind(kind) && (
            <Button
              component={Link}
              to={`/library/${kind}/new`}
              leftSection={<IconPlus size={17} />}
            >
              New {singularLabels[kind]}
            </Button>
          )}
        </Group>
        <Tabs
          value={kind}
          onChange={(value) => value && navigate(`/library/${value}?${params}`)}
        >
          <Tabs.List>
            {Object.entries(kindLabels).map(([value, label]) => (
              <Tabs.Tab key={value} value={value}>
                {label}
              </Tabs.Tab>
            ))}
            <Tabs.Tab value="load-cases">Load cases</Tabs.Tab>
          </Tabs.List>
        </Tabs>
        <LibraryBrowser kind={kind} refresh={loadCaseRefresh} />
      </Stack>
    </Container>
  );
}
