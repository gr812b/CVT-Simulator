import { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Container,
  Group,
  Loader,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { Link } from 'react-router-dom';
import { useAuth } from '@contexts/AuthContext';
import { listExperiments, message, type ExperimentItem } from './api';
import { LoadCaseEditor } from './LoadCaseEditor';

export function LoadCaseLibrary({
  publicView = false,
}: {
  publicView?: boolean;
}) {
  const { session } = useAuth();
  const [items, setItems] = useState<ExperimentItem[]>([]);
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [editor, setEditor] = useState<{ id: string | null } | null>(null);
  useEffect(() => {
    let disposed = false;
    setLoading(true);
    setError(null);
    void listExperiments('scenarios')
      .then((next) => {
        if (!disposed) setItems(next);
      })
      .catch((cause) => {
        if (!disposed) setError(message(cause));
      })
      .finally(() => {
        if (!disposed) setLoading(false);
      });
    return () => {
      disposed = true;
    };
  }, [retry]);
  const visible = items.filter(
    (item) =>
      !item.archived &&
      (scope !== 'own' || item.owned) &&
      (scope !== 'samples' || item.sample) &&
      `${item.name} ${item.description}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <Container size="xl" px={publicView ? 0 : undefined} py="lg">
      <Stack>
        <Group justify="space-between">
          <div>
            <Title order={publicView ? 2 : 1}>Load cases</Title>
            <Text c="dimmed">
              Reusable roads, hills and whoops. Choose a saved case for any
              vehicle.
            </Text>
          </div>
          {session && (
            <Button onClick={() => setEditor({ id: null })}>
              New load case
            </Button>
          )}
        </Group>
        <Group justify="space-between">
          <SegmentedControl
            value={scope}
            onChange={setScope}
            data={[
              { value: 'all', label: 'All public' },
              { value: 'samples', label: 'Defaults' },
              ...(session ? [{ value: 'own', label: 'Mine' }] : []),
            ]}
          />
          <TextInput
            aria-label="Search load cases"
            placeholder="Search load cases"
            value={query}
            onChange={(e) => setQuery(e.currentTarget.value)}
          />
        </Group>
        {loading ? (
          <Loader aria-label="Loading load cases" />
        ) : error ? (
          <Alert color="red">
            {error}
            <Button onClick={() => setRetry((x) => x + 1)}>Try again</Button>
          </Alert>
        ) : (
          <>
            {!visible.length && (
              <Text>
                No matching load cases. Create one or choose another filter.
              </Text>
            )}
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
              {visible.map((item) => (
                <Paper key={item.id} withBorder p="lg">
                  <Stack h="100%" justify="space-between">
                    <Stack gap="xs">
                      <Group>
                        <Badge variant="light">
                          {item.sample
                            ? 'Default'
                            : item.owned
                              ? 'Mine · public'
                              : 'Public'}
                        </Badge>
                        <Text size="xs">Revision {item.revision_number}</Text>
                      </Group>
                      <Title order={3} size="h4">
                        {item.name}
                      </Title>
                      <Text size="sm" c="dimmed" lineClamp={3}>
                        {item.description ||
                          'A saved road profile with initial conditions and run settings.'}
                      </Text>
                    </Stack>
                    <Group>
                      <Button
                        component={Link}
                        to={`/catalog/load-cases/${item.id}`}
                        variant="light"
                      >
                        View load case
                      </Button>
                      {session && (
                        <>
                          <Button
                            variant="default"
                            onClick={() => setEditor({ id: item.id })}
                          >
                            {item.owned ? 'Edit' : 'Customize'}
                          </Button>
                          <Button
                            component={Link}
                            to={`/input?scenario=${item.id}`}
                            variant="subtle"
                          >
                            Use in a run
                          </Button>
                        </>
                      )}
                    </Group>
                  </Stack>
                </Paper>
              ))}
            </SimpleGrid>
          </>
        )}
        {editor && (
          <LoadCaseEditor
            key={editor.id ?? 'new'}
            id={editor.id}
            onClose={() => setEditor(null)}
            onSaved={() => {
              setEditor(null);
              setRetry((x) => x + 1);
            }}
          />
        )}
      </Stack>
    </Container>
  );
}
