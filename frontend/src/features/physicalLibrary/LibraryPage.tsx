import { LibraryCard } from './LibraryCard';
import { LoadCaseEditor } from '../experiments/LoadCaseEditor';
import { LoadCaseLibrary } from '../experiments/LoadCaseLibrary';
import { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Checkbox,
  Container,
  Group,
  Box,
  LoadingOverlay,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Tabs,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { IconPlus, IconSearch } from '@tabler/icons-react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import {
  isPhysicalKind,
  kindLabels,
  listPhysical,
  singularLabels,
  type PhysicalItem,
  type PhysicalKind,
} from './api';

export function LibraryPage() {
  const { kind } = useParams();
  const navigate = useNavigate();
  const [newLoadCase, setNewLoadCase] = useState(false);
  const [loadCaseRefresh, setLoadCaseRefresh] = useState(0);
  if (!isPhysicalKind(kind) && kind !== 'load-cases')
    return <Navigate to="/library/setups" replace />;
  return (
    <Container size="xl" py="lg">
      {newLoadCase && <LoadCaseEditor id={null} onClose={() => setNewLoadCase(false)} onSaved={() => { setNewLoadCase(false); setLoadCaseRefresh(x => x + 1); }} />}
      <Stack gap="xl">
        <Group justify="space-between" align="start" mih={78}>
          <div>
            <Title order={1}>Physical library</Title>
            <Text c="dimmed" mt="xs">
              Reusable vehicles, components and load cases for your simulations.
            </Text>
          </div>
          {kind === 'load-cases' && <Button leftSection={<IconPlus size={17} />} onClick={() => setNewLoadCase(true)}>New load case</Button>}
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
          onChange={(value) => value && navigate(`/library/${value}`)}
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
        {kind === 'load-cases' ? (
          <LoadCaseLibrary embedded key={loadCaseRefresh} />
        ) : (
          <LibraryList key={kind} kind={kind} />
        )}
      </Stack>
    </Container>
  );
}

function LibraryList({ kind }: { kind: PhysicalKind }) {
  const [scope, setScope] = useState<'own' | 'samples'>('own');
  const [query, setQuery] = useState('');
  const [archived, setArchived] = useState(false);
  const [items, setItems] = useState<PhysicalItem[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setBusy(true);
    setError(null);
    listPhysical(kind, scope, scope === 'own' && archived, controller.signal)
      .then((next) => {
        if (!controller.signal.aborted) setItems(next);
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : 'Unable to load your library.',
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [kind, scope, archived, retry]);
  const visible = items.filter((item) =>
    `${item.name} ${item.description} ${item.source_label}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Button component={Link} to={`/catalog?kind=${kind}`} variant="subtle">
          Browse public library
        </Button>
        <SegmentedControl
          value={scope}
          onChange={(value) =>
            setScope(value === 'samples' ? 'samples' : 'own')
          }
          data={[
            { value: 'own', label: 'My library' },
            { value: 'samples', label: 'CINDER defaults' },
          ]}
        />
        <Checkbox
          disabled={scope !== 'own'}
          style={{ visibility: scope === 'own' ? 'visible' : 'hidden' }}
          label="Include archived"
          checked={archived}
          onChange={(event) => setArchived(event.currentTarget.checked)}
        />
        <TextInput
          aria-label="Search library"
          placeholder={`Search ${kindLabels[kind].toLowerCase()}`}
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
          leftSection={<IconSearch size={16} />}
        />
      </Group>
      <Text size="sm" c="dimmed" mih={42}>
        {scope === 'samples'
          ? 'CINDER baselines and illustrative variations. Open a default to make your own copy.'
          : 'Your saved items. Use the defaults as a starting point or create your own.'}
      </Text>
      <Box pos="relative" mih={360} aria-busy={busy}>
        <LoadingOverlay
          visible={busy}
          loaderProps={{ 'aria-label': 'Loading your library' }}
        />
        <div inert={busy}>
          {error ? (
            <Alert color="red" title="Library unavailable" role="alert">
              {error}
              <Button
                variant="subtle"
                onClick={() => setRetry((value) => value + 1)}
              >
                Try again
              </Button>
            </Alert>
          ) : visible.length ? (
            <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }}>
              {visible.map((item) => (
                <LibraryCard key={item.id} name={item.name} description={item.description} author={item.author}
                  badge={item.archived ? 'Archived' : item.owned ? 'My library' : 'CINDER default'}
                  actions={<Button component={Link} to={`/library/${kind}/${item.id}`} variant="light" fullWidth>{item.owned ? 'Open' : 'View default'}</Button>}>
                  {item.validation_status !== 'valid' && <Badge color="yellow">Needs attention</Badge>}
                </LibraryCard>
              ))}
            </SimpleGrid>
          ) : (
            <Paper withBorder p="xl">
              <Stack align="start">
                <Title order={2} size="h3">
                  {query
                    ? 'No matching items'
                    : `No ${kindLabels[kind].toLowerCase()} here yet`}
                </Title>
                <Text c="dimmed">
                  {query
                    ? 'Try another name or source.'
                    : 'Start with the project’s complete baseline or enter your own measurements.'}
                </Text>
                {!query && (
                  <Group>
                    <Button component={Link} to={`/library/${kind}/new`}>
                      Create {singularLabels[kind]}
                    </Button>
                    {scope === 'own' && (
                      <Button
                        variant="default"
                        onClick={() => setScope('samples')}
                      >
                        Browse defaults
                      </Button>
                    )}
                  </Group>
                )}
              </Stack>
            </Paper>
          )}
        </div>
      </Box>
    </Stack>
  );
}
