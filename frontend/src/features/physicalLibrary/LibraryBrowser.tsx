import { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Checkbox,
  Group,
  LoadingOverlay,
  Pagination,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { IconSearch } from '@tabler/icons-react';
import { Link, useSearchParams } from 'react-router-dom';
import { ActionButton as Button } from '@components/button/ActionButton';
import { useAuth } from '@contexts/AuthContext';
import { LibraryCard } from './LibraryCard';
import { listPhysical, type PhysicalKind, type PhysicalItem } from './api';
import { listExperiments, message } from '../experiments/api';

export type LibraryCategory = PhysicalKind | 'load-cases';
type Card = Pick<
  PhysicalItem,
  | 'id'
  | 'name'
  | 'description'
  | 'author'
  | 'author_id'
  | 'owned'
  | 'sample'
  | 'archived'
> & { href: string };

/** Every physical category, including load cases, shares filters and results. */
export function LibraryBrowser({
  kind,
  publicView = false,
  authorId,
  refresh = 0,
}: {
  kind: LibraryCategory;
  publicView?: boolean;
  authorId?: string;
  refresh?: number;
}) {
  const { session } = useAuth();
  const [params, setParams] = useSearchParams();
  const scope = authorId
    ? 'all'
    : params.get('scope') === 'samples'
      ? 'samples'
      : params.get('scope') === 'own' && session
        ? 'own'
        : publicView
          ? 'all'
          : 'own';
  const query = params.get('q') ?? '';
  const archived = params.get('archived') === '1';
  const page = Math.max(1, Number(params.get('page')) || 1);
  const [items, setItems] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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
    const abort = new AbortController();
    setLoading(true);
    setError(null);
    const load = async (): Promise<Card[]> => {
      if (kind === 'load-cases')
        return (
          await listExperiments('scenarios', undefined, {
            authorId,
            signal: abort.signal,
            includeArchived: archived && scope === 'own',
          })
        ).map((item) => ({
          ...item,
          sample: !!item.sample,
          description: item.description ?? '',
          href: `/catalog/load-cases/${item.id}`,
        }));
      return (
        await listPhysical(
          kind,
          scope,
          archived && scope === 'own',
          abort.signal,
          authorId,
        )
      ).map((item) => ({
        ...item,
        href: `/library/${kind}/${item.id}`,
      }));
    };
    void load()
      .then((next) => {
        if (!abort.signal.aborted) setItems(next);
      })
      .catch((cause) => {
        if (!abort.signal.aborted) setError(message(cause));
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [kind, scope, archived, refresh, retry, authorId]);
  const visible = items.filter(
    (item) =>
      (scope !== 'own' || item.owned) &&
      (scope !== 'samples' || item.sample) &&
      (!item.archived || (scope === 'own' && archived)) &&
      `${item.name} ${item.description} ${item.author}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const currentPage = Math.min(
    page,
    Math.max(1, Math.ceil(visible.length / 24)),
  );
  return (
    <Stack gap="lg">
      <Group justify="space-between" align="center">
        {!authorId && (
          <SegmentedControl
            aria-label="Library source"
            value={scope}
            onChange={(value) => update('scope', value)}
            data={[
              ...(publicView ? [{ value: 'all', label: 'All public' }] : []),
              ...(session ? [{ value: 'own', label: 'My library' }] : []),
              { value: 'samples', label: 'CINDER defaults' },
            ]}
          />
        )}
        <TextInput
          aria-label="Search library"
          placeholder="Search names or authors"
          value={query}
          onChange={(event) => update('q', event.currentTarget.value)}
          leftSection={<IconSearch size={16} />}
        />
        {!publicView && (
          <Button
            component={Link}
            to={`/catalog?kind=${kind}`}
            variant="subtle"
          >
            Browse public library
          </Button>
        )}
      </Group>
      <Group justify="space-between" mih={28}>
        <Text size="sm" c="dimmed">
          {scope === 'samples'
            ? 'CINDER defaults'
            : scope === 'own'
              ? 'Your saved items'
              : 'Community configurations'}{' '}
          · {loading ? 'Loading…' : `${visible.length} items`}
        </Text>
        {session && !authorId && (
          <Checkbox
            label="Include archived"
            checked={archived}
            disabled={scope !== 'own'}
            style={{ visibility: scope === 'own' ? 'visible' : 'hidden' }}
            onChange={(event) =>
              update('archived', event.currentTarget.checked ? '1' : '')
            }
          />
        )}
      </Group>
      <Box pos="relative" mih={360} aria-busy={loading}>
        <LoadingOverlay
          visible={loading}
          loaderProps={{ 'aria-label': 'Loading library' }}
        />
        <div inert={loading}>
          {error ? (
            <Alert color="red" title="Library unavailable">
              {error}
              <Button variant="subtle" onClick={() => setRetry((x) => x + 1)}>
                Try again
              </Button>
            </Alert>
          ) : visible.length ? (
            <SimpleGrid cols={{ base: 1, md: 2, xl: 3 }}>
              {visible
                .slice((currentPage - 1) * 24, currentPage * 24)
                .map((item) => (
                  <LibraryCard
                    key={item.id}
                    name={item.name}
                    description={item.description}
                    author={item.author}
                    authorId={item.author_id}
                    badge={
                      item.archived
                        ? 'Archived'
                        : item.sample
                          ? 'CINDER default'
                          : item.owned
                            ? 'My library'
                            : 'Community'
                    }
                    actions={
                      <>
                        <Button
                          component={Link}
                          to={item.href}
                          variant="light"
                          fullWidth
                        >
                          View{' '}
                          {kind === 'load-cases'
                            ? 'load case'
                            : 'configuration'}
                        </Button>
                        {kind === 'cvts' && (
                          <Button
                            component={Link}
                            to={`${item.href}#tunes`}
                            fullWidth
                          >
                            Browse tunes
                          </Button>
                        )}
                      </>
                    }
                  />
                ))}
            </SimpleGrid>
          ) : (
            !loading && (
              <Paper withBorder p="xl">
                <Text fw={600}>No matching items</Text>
                <Text c="dimmed">
                  Choose another source or change your search.
                </Text>
              </Paper>
            )
          )}
        </div>
      </Box>
      {visible.length > 24 && (
        <Group justify="center" py="xl">
          <Pagination
            value={currentPage}
            total={Math.ceil(visible.length / 24)}
            onChange={(next) => update('page', String(next))}
          />
        </Group>
      )}
    </Stack>
  );
}
