import { LibraryCard } from '../physicalLibrary/LibraryCard';
import { useEffect, useState } from 'react';
import {
  Alert,
  Group,
  Box,
  LoadingOverlay,
  Pagination,
  Paper,
  Tabs,
  SimpleGrid,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { useDebouncedValue } from '@mantine/hooks';
import { Link, useSearchParams } from 'react-router-dom';
import { LoadCaseLibrary } from '../experiments/LoadCaseLibrary';
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
      <Box pos="relative" mih={400} aria-busy={loading}>
        <LoadingOverlay
          visible={loading}
          loaderProps={{ 'aria-label': 'Loading public library' }}
        />
        <div inert={loading}>
          {error ? (
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
                  {data.total === 1 ? 'publication' : 'publications'}. The
                  latest saved configurations appear here.
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
                      <LibraryCard key={item.id} name={item.name} description={item.description} author={item.author}
                        badge={item.sample ? `${kindLabels[item.kind]} · Default` : kindLabels[item.kind]}
                        actions={<>
                          <Button component={Link} to={`/catalog/${item.id}`} variant="light">View configuration</Button>
                          {item.kind === 'cvts' && <Button component={Link} to={`/catalog/${item.id}#tunes`} variant="filled">Browse tunes</Button>}
                        </>}>
                        <SimpleGrid cols={2}>{item.properties.slice(0, 2).map(property => <div key={property.key}>
                          <Text size="xs" c="dimmed">{property.label}</Text><Text size="sm">{formatMetric(property)}</Text>
                        </div>)}</SimpleGrid>
                      </LibraryCard>
                    ))}
                  </SimpleGrid>
                )}
                {data.total > 24 && (
                  <Group justify="center" py="xl"><Pagination
                    total={Math.ceil(data.total / 24)}
                    value={page}
                    onChange={(value) => update('page', String(value))}
                  /></Group>
                )}
              </>
            )
          )}
        </div>
      </Box>
    </>
  );
}

export function PublicLibrary() {
  const [params, setParams] = useSearchParams();
  const requested = params.get('kind') ?? 'setups';
  const selected = requested === 'tunes' ? 'cvts' : requested;
  const kind =
    ['load-cases', 'runs'].includes(selected) || isPhysicalKind(selected)
      ? selected
      : 'setups';
  return (
    <CatalogFrame>
      <Title order={1}>Public library</Title>
      <Text c="dimmed">
        Free accounts share saved configurations, load cases, tunes and
        simulation results. Find tunes on each CVT’s page.
      </Text>
      <Tabs value={kind} onChange={(next) => next && setParams({ kind: next })}>
        <Tabs.List>
          {Object.entries(kindLabels).map(([value, label]) => (
            <Tabs.Tab key={value} value={value}>
              {label}
            </Tabs.Tab>
          ))}
          <Tabs.Tab value="load-cases">Load cases</Tabs.Tab>
          <Tabs.Tab value="runs">Runs</Tabs.Tab>
        </Tabs.List>
      </Tabs>
      {kind === 'load-cases' ? (
        <LoadCaseLibrary publicView />
      ) : kind === 'runs' ? (
        <PublicRunList />
      ) : (
        <PhysicalCatalog kind={kind as PhysicalKind} />
      )}
    </CatalogFrame>
  );
}
