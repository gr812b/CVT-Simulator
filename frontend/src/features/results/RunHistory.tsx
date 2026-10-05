import { RunStatusBadge } from './RunStatusBadge';
import { AuthorLink } from '../community/AuthorLink';
import { useEffect, useState } from 'react';
import {
  Alert,
  Container,
  Group,
  Loader,
  Pagination,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { useDebouncedValue } from '@mantine/hooks';
import { Link, useSearchParams } from 'react-router-dom';
import { getHistory, type HistoryQuery, type RunHistoryPage } from './api';
import { isActive, message } from '../experiments/api';

const statuses: NonNullable<HistoryQuery['status']>[] = [
  'queued',
  'running',
  'completed',
  'failed',
  'timed_out',
  'cancelled',
  'validating',
];
const sources: NonNullable<HistoryQuery['source']>[] = [
  'experiment',
  'library',
  'direct',
];

export function RunHistory({
  publicView = false,
  authorId,
}: {
  publicView?: boolean;
  authorId?: string;
}) {
  const [params, setParams] = useSearchParams();
  const search = params.get('q') ?? '';
  const [query] = useDebouncedValue(search, 250);
  const [data, setData] = useState<RunHistoryPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const requestedPage = Number(params.get('page'));
  const page = Number.isSafeInteger(requestedPage)
    ? Math.max(1, requestedPage)
    : 1;
  const status = statuses.find((value) => value === params.get('status'));
  const source = sources.find((value) => value === params.get('source'));
  const from = params.get('from') ?? '';
  const through = params.get('through') ?? '';
  const oldest = params.get('sort') === 'oldest';
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
    let timer: ReturnType<typeof setTimeout>;
    const fetchPage = async () => {
      try {
        const date = (value: string, end: boolean) => {
          if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return undefined;
          const parsed = new Date(
            `${value}T${end ? '23:59:59.999' : '00:00:00'}`,
          );
          return Number.isFinite(parsed.valueOf())
            ? parsed.toISOString()
            : undefined;
        };
        const result = await getHistory(
          {
            q: query,
            scope: publicView ? 'all' : 'own',
            author_id: authorId,
            status,
            source,
            since: date(from, false),
            until: date(through, true),
            oldest_first: oldest,
            offset: (page - 1) * 24,
            limit: 24,
          },
          controller.signal,
        );
        if (controller.signal.aborted) return;
        setData(result);
        setError(null);
        setLoading(false);
        if (result.items.some((item) => isActive(item.run)))
          timer = setTimeout(fetchPage, 2500);
      } catch (cause) {
        if (!controller.signal.aborted) {
          setError(message(cause));
          setLoading(false);
        }
      }
    };
    setLoading(true);
    void fetchPage();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [
    query,
    status,
    source,
    from,
    through,
    oldest,
    page,
    retry,
    publicView,
    authorId,
  ]);
  return (
    <Container
      size="xl"
      w="100%"
      px={publicView ? 0 : undefined}
      py={publicView ? 0 : 'lg'}
    >
      <Stack gap="lg">
        {!publicView && (
          <Group justify="space-between">
            <div>
              <Title order={1}>Runs & results</Title>
              <Text c="dimmed" mt="xs">
                Return to saved inputs, results and the experiments that
                produced them.
              </Text>
            </div>
            <Button component={Link} to="/input">
              New experiment
            </Button>
          </Group>
        )}
        <Paper withBorder p="lg">
          <Stack>
            <TextInput
              label="Search runs"
              placeholder="Run, setup, tune, scenario or run ID"
              value={search}
              onChange={(event) => update('q', event.currentTarget.value)}
            />
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 5 }}>
              <Select
                label="Status"
                placeholder="All statuses"
                clearable
                data={statuses.map((value) => ({
                  value,
                  label: value.replace(/_/g, ' '),
                }))}
                value={status ?? null}
                onChange={(value) => update('status', value ?? '')}
              />
              <Select
                label="Source"
                placeholder="All sources"
                clearable
                data={sources}
                value={source ?? null}
                onChange={(value) => update('source', value ?? '')}
              />
              <TextInput
                type="date"
                label="Submitted from"
                value={from}
                onChange={(event) => update('from', event.currentTarget.value)}
              />
              <TextInput
                type="date"
                label="Submitted through"
                value={through}
                onChange={(event) =>
                  update('through', event.currentTarget.value)
                }
              />
              <Select
                label="Order"
                value={oldest ? 'oldest' : 'newest'}
                data={[
                  { value: 'newest', label: 'Newest first' },
                  { value: 'oldest', label: 'Oldest first' },
                ]}
                onChange={(value) => update('sort', value ?? '')}
              />
            </SimpleGrid>
            <Group>
              <Text size="xs" c="dimmed">
                Dates use your local timezone.
              </Text>
              <Button
                variant="subtle"
                size="xs"
                onClick={() => {
                  setParams(publicView ? { kind: 'runs' } : {});
                }}
              >
                Clear filters
              </Button>
              <Button
                variant="subtle"
                size="xs"
                onClick={() => setRetry((value) => value + 1)}
              >
                Refresh runs
              </Button>
            </Group>
          </Stack>
        </Paper>
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
        ) : loading ? (
          <Loader aria-label="Loading run history" />
        ) : (
          data && (
            <>
              <Text size="sm" c="dimmed">
                {data.total} {data.total === 1 ? 'run' : 'runs'}
              </Text>
              {!data.items.length ? (
                <Paper withBorder p="xl">
                  <Title order={2} size="h3">
                    No runs match these filters
                  </Title>
                  <Text mt="sm">
                    Start an experiment or clear the filters to see your earlier
                    work.
                  </Text>
                </Paper>
              ) : (
                <Stack>
                  {data.items.map(({ run, references }) => (
                    <Paper withBorder p="lg" key={run.id}>
                      <div className="public-run-row">
                        <div style={{ minWidth: 0 }}>
                          <Text fw={600} style={{ overflowWrap: 'anywhere' }}>
                            {run.name}
                          </Text>
                          <Text size="sm" c="dimmed">
                            By{' '}
                            <AuthorLink name={run.author} id={run.author_id} />{' '}
                            · {new Date(run.submitted_at).toLocaleDateString()}
                          </Text>
                          <Text size="xs" c="dimmed" lineClamp={1}>
                            {references.map((ref) => ref.name).join(' · ')}
                          </Text>
                        </div>
                        <RunStatusBadge status={run.status} />
                        <Button
                          component={Link}
                          to={`/runs/${run.id}`}
                          variant="light"
                        >
                          View run
                        </Button>
                      </div>
                    </Paper>
                  ))}
                </Stack>
              )}
              {data.total > 24 && (
                <Group justify="center" py="xl">
                  <Pagination
                    total={Math.ceil(data.total / 24)}
                    value={page}
                    onChange={(value) => update('page', String(value))}
                  />
                </Group>
              )}
            </>
          )
        )}
      </Stack>
    </Container>
  );
}
