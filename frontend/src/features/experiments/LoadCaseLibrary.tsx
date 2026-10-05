import { LibraryCard } from '../physicalLibrary/LibraryCard';
import { useEffect, useState } from 'react';
import {
  Alert,
  Container,
  Group,
  Loader,
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
  embedded = false,
}: {
  publicView?: boolean;
  embedded?: boolean;
}) {
  const { session } = useAuth();
  const [items, setItems] = useState<ExperimentItem[]>([]);
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState(publicView ? 'all' : 'own');
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
    <Container
      size="xl"
      px={publicView || embedded ? 0 : undefined}
      py={embedded ? 0 : 'lg'}
      w="100%"
      mih={480}
    >
      <Stack>
        {!embedded && <Group justify="space-between">
          <div>
            <Title order={publicView || embedded ? 2 : 1}>Load cases</Title>
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
        </Group>}
        <Group justify="space-between">
          <SegmentedControl
            value={scope}
            onChange={setScope}
            data={[
              ...(publicView ? [{ value: 'all', label: 'All public' }] : []),
              { value: 'samples', label: 'Samples' },
              ...(session ? [{ value: 'own', label: 'My library' }] : []),
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
                <LibraryCard key={item.id} name={item.name} description={item.description} author={item.author}
                  badge={item.sample ? 'CINDER default' : item.owned ? 'My library' : 'Public'}
                  actions={<>
                    <Button component={Link} to={`/catalog/load-cases/${item.id}`} variant="light" fullWidth>View load case</Button>
                    {session && <Group grow>
                      <Button variant="default" onClick={() => setEditor({ id: item.id })}>{item.owned ? 'Edit' : 'Customize'}</Button>
                      <Button component={Link} to={`/input?scenario=${item.id}`} variant="subtle">Use in a run</Button>
                    </Group>}
                  </>} />
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
