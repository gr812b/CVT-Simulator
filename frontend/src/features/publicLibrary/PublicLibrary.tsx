import { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Group,
  Loader,
  Pagination,
  Paper,
  Tabs,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { useDebouncedValue } from '@mantine/hooks';
import { Link, useSearchParams } from 'react-router-dom';
import { LoadCaseLibrary } from '../experiments/LoadCaseLibrary';
import { PublicTuneList } from './PublicExperiment';
import { PublicRunList } from './PublicRuns';
import {
  kindLabels,
  isPhysicalKind,
  type PhysicalKind,
} from '../physicalLibrary/api';
import { CatalogFrame } from './CatalogFrame';
import { browsePublications, type PublicationPage } from './api';
import { formatMetric } from '../results/api';
import { message } from '../experiments/api';

function PhysicalCatalog({ kind }: { kind: PhysicalKind }) {
  const [params, setParams] = useSearchParams();
  const search = params.get('q') ?? '';
  const [query] = useDebouncedValue(search, 250);
  const page = Math.max(1, Number(params.get('page')) || 1);
  const [data, setData] = useState<PublicationPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const update = (key: string, value: string) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set(key, value);
        else next.delete(key);
        if (key !== 'page') next.delete('page');
        return next;
      },
      { replace: key === 'q' },
    );
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void browsePublications(
      { kind, q: query, offset: (page - 1) * 24, limit: 24 },
      controller.signal,
    )
      .then((result) => {
        if (!controller.signal.aborted) setData(result);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(message(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [kind, query, page, retry]);
  return (
    <>
      <div>
        <Title order={1}>Public configurations</Title>
        <Text c="dimmed" mt="sm">
          Inspect a published configuration, then make an independent copy for
          your own measurements and experiments.
        </Text>
      </div>
      <Group justify="space-between">
        <TextInput
          aria-label="Search public library"
          placeholder="Search names, sources or authors"
          value={search}
          onChange={(event) => update('q', event.currentTarget.value)}
          miw={260}
        />
      </Group>
      {loading ? (
        <Loader aria-label="Loading public library" />
      ) : error ? (
        <Alert color="red" role="alert">
          {error}
          <Button
            variant="subtle"
            onClick={() => setRetry((value) => value + 1)}
          >
            Try again
          </Button>
        </Alert>
      ) : (
        data && (
          <>
            <Text size="sm" c="dimmed">
              {data.total} listed{' '}
              {data.total === 1 ? 'publication' : 'publications'}. The latest
              saved revisions appear here.
            </Text>
            {!data.items.length ? (
              <Paper withBorder p="xl">
                <Title order={2} size="h3">
                  No matching publications
                </Title>
                <Text mt="sm">
                  Try another search, or save an item from your physical
                  library.
                </Text>
              </Paper>
            ) : (
              <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
                {data.items.map((item) => (
                  <Paper key={item.id} withBorder p="lg">
                    <Stack h="100%" justify="space-between">
                      <Stack gap="sm">
                        <Group>
                          <Badge>{kindLabels[item.kind]}</Badge>
                          {item.sample && (
                            <Badge color="blue" variant="outline">
                              Catalog default
                            </Badge>
                          )}
                        </Group>
                        <Title
                          order={2}
                          size="h3"
                          style={{ overflowWrap: 'anywhere' }}
                        >
                          {item.name}
                        </Title>
                        <Text size="sm" c="dimmed" lineClamp={3}>
                          {item.description ||
                            'A fixed configuration with its required component values included.'}
                        </Text>
                        <Text size="sm">By {item.author}</Text>
                        <Text size="xs" c="dimmed">
                          Publication {item.publication_number} · source
                          revision {item.revision_number}
                        </Text>
                        <SimpleGrid cols={2}>
                          {item.properties.slice(0, 2).map((property) => (
                            <div key={property.key}>
                              <Text size="xs" c="dimmed">
                                {property.label}
                              </Text>
                              <Text size="sm">{formatMetric(property)}</Text>
                            </div>
                          ))}
                        </SimpleGrid>
                        {item.source_label && (
                          <Text size="xs" c="dimmed">
                            Source: {item.source_label}
                          </Text>
                        )}
                      </Stack>
                      <Button
                        component={Link}
                        to={`/catalog/${item.id}`}
                        variant="light"
                      >
                        View configuration
                      </Button>
                    </Stack>
                  </Paper>
                ))}
              </SimpleGrid>
            )}
            {data.total > 24 && (
              <Pagination
                total={Math.ceil(data.total / 24)}
                value={page}
                onChange={(value) => update('page', String(value))}
              />
            )}
          </>
        )
      )}
    </>
  );
}

export function PublicLibrary() {
  const [params, setParams] = useSearchParams();
  const selected = params.get('kind') ?? 'setups';
  const kind =
    ['load-cases', 'tunes', 'runs'].includes(selected) ||
    isPhysicalKind(selected)
      ? selected
      : 'setups';
  return (
    <CatalogFrame>
      <Title order={1}>Public library</Title>
      <Text c="dimmed">
        Free accounts share saved configurations, load cases, tunes and
        simulation results.
      </Text>
      <Tabs value={kind} onChange={(next) => next && setParams({ kind: next })}>
        <Tabs.List>
          {Object.entries(kindLabels).map(([value, label]) => (
            <Tabs.Tab key={value} value={value}>
              {label}
            </Tabs.Tab>
          ))}
          <Tabs.Tab value="load-cases">Load cases</Tabs.Tab>
          <Tabs.Tab value="tunes">Tunes</Tabs.Tab>
          <Tabs.Tab value="runs">Runs</Tabs.Tab>
        </Tabs.List>
      </Tabs>
      {kind === 'load-cases' ? (
        <LoadCaseLibrary publicView />
      ) : kind === 'tunes' ? (
        <PublicTuneList />
      ) : kind === 'runs' ? (
        <PublicRunList />
      ) : (
        <PhysicalCatalog kind={kind as PhysicalKind} />
      )}
    </CatalogFrame>
  );
}
