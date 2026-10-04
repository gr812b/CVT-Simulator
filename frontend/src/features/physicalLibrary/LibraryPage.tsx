import { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Checkbox,
  Container,
  Group,
  Loader,
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
  if (!isPhysicalKind(kind)) return <Navigate to="/library/setups" replace />;
  return <LibraryList key={kind} kind={kind} />;
}

function LibraryList({ kind }: { kind: PhysicalKind }) {
  const navigate = useNavigate();
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
      .then(setItems)
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
    <Container size="xl" py="lg">
      <Stack gap="xl">
        <Group justify="space-between" align="start">
          <div>
            <Title order={1}>Physical library</Title>
            <Text c="dimmed" mt="xs">
              Build a vehicle from reusable components. Saved revisions keep
              every setup’s inputs fixed.
            </Text>
          </div>
          <Button
            component={Link}
            to={`/library/${kind}/new`}
            leftSection={<IconPlus size={17} />}
          >
            New {singularLabels[kind]}
          </Button>
        </Group>
        <Tabs
          value={kind}
          onChange={(value) => value && navigate(`/library/${value}`)}
        >
          <Tabs.List>
            {(Object.keys(kindLabels) as PhysicalKind[]).map((value) => (
              <Tabs.Tab key={value} value={value}>
                {kindLabels[value]}
              </Tabs.Tab>
            ))}
          </Tabs.List>
        </Tabs>
        <Group justify="space-between">
          <Button
            component={Link}
            to={`/catalog?kind=${kind}`}
            variant="subtle"
          >
            Browse public library
          </Button>
          <SegmentedControl
            value={scope}
            onChange={(value) =>
              setScope(value === 'samples' ? 'samples' : 'own')
            }
            data={[
              { value: 'own', label: 'My library' },
              { value: 'samples', label: 'Samples' },
            ]}
          />
          {scope === 'own' && (
            <Checkbox
              label="Include archived"
              checked={archived}
              onChange={(event) => setArchived(event.currentTarget.checked)}
            />
          )}
          <TextInput
            aria-label="Search library"
            placeholder={`Search ${kindLabels[kind].toLowerCase()}`}
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
            leftSection={<IconSearch size={16} />}
          />
        </Group>
        {scope === 'samples' && (
          <Text size="sm" c="dimmed">
            Project baselines and clearly labeled illustrative variations. Open
            any sample to copy a fixed revision into your own library.
          </Text>
        )}
        {busy ? (
          <Group>
            <Loader size="sm" />
            <Text role="status">Loading your library…</Text>
          </Group>
        ) : error ? (
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
              <Paper key={item.id} withBorder p="lg" radius="lg">
                <Stack h="100%" justify="space-between">
                  <Stack gap="sm">
                    <Group justify="space-between">
                      <Badge variant="light">
                        Revision {item.revision_number}
                      </Badge>
                      <Badge
                        variant="outline"
                        color={
                          item.archived ? 'gray' : item.owned ? 'teal' : 'blue'
                        }
                      >
                        {item.archived
                          ? 'Archived'
                          : item.owned
                            ? 'My item · public'
                            : 'Sample'}
                      </Badge>
                    </Group>
                    <Title order={2} size="h4">
                      {item.name}
                    </Title>
                    <Text c="dimmed" size="sm" lineClamp={3}>
                      {item.description || 'A saved physical configuration.'}
                    </Text>
                    {item.validation_status !== 'valid' && (
                      <Badge color="yellow" variant="light">
                        Needs attention
                      </Badge>
                    )}
                    {item.source_label && (
                      <Text size="xs" c="dimmed">
                        Source: {item.source_label}
                      </Text>
                    )}
                  </Stack>
                  <Button
                    component={Link}
                    to={`/library/${kind}/${item.id}`}
                    variant="light"
                    fullWidth
                    mt="md"
                  >
                    {item.owned ? 'Open' : 'View sample'}
                  </Button>
                </Stack>
              </Paper>
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
                      Browse samples
                    </Button>
                  )}
                </Group>
              )}
            </Stack>
          </Paper>
        )}
      </Stack>
    </Container>
  );
}
