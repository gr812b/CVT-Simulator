import { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Group,
  Loader,
  Pagination,
  Paper,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ActionButton as Button } from '@components/button/ActionButton';
import { getSimulationResult, type CompletedSimulationRun } from '@api/client';
import {
  getHistory,
  inspectRun,
  type RunHistoryPage,
  type RunInspection,
} from '../results/api';
import { ResultDetails } from '../results/ResultDetails';
import { message } from '../experiments/api';
import { SimulationPlayback } from '@pages/playback/SimulationPlayback';
import { CatalogFrame } from './CatalogFrame';

export function PublicRunList() {
  const [params, setParams] = useSearchParams();
  const search = params.get('q') ?? '';
  const [query] = useDebouncedValue(search, 250);
  const page = Math.max(1, Number(params.get('page')) || 1);
  const [data, setData] = useState<RunHistoryPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    setError(null);
    void getHistory(
      { scope: 'all', q: query, limit: 24, offset: (page - 1) * 24 },
      abort.signal,
    )
      .then((next) => {
        if (!abort.signal.aborted) setData(next);
      })
      .catch((cause) => {
        if (!abort.signal.aborted) setError(message(cause));
      });
    return () => abort.abort();
  }, [page, query]);
  return (
    <Stack>
      <Title order={2}>Public runs</Title>
      <TextInput
        aria-label="Search public runs"
        placeholder="Search runs and setup names"
        value={search}
        onChange={(e) =>
          setParams(
            { kind: 'runs', q: e.currentTarget.value },
            { replace: true },
          )
        }
      />
      {error && <Alert color="red">{error}</Alert>}
      {!data && !error && <Loader />}
      {data?.items.map((item) => (
        <Paper withBorder p="lg" key={item.run.id}>
          <div className="public-run-row">
            <div style={{ minWidth: 0 }}>
              <Text fw={600} style={{ overflowWrap: 'anywhere' }}>
                {item.run.name}
              </Text>
              <Text size="sm" c="dimmed">
                By {item.run.author} · {new Date(item.run.submitted_at).toLocaleDateString()}
              </Text>
              <Text size="xs" c="dimmed" lineClamp={1}>
                {item.references.map(ref => ref.name).slice(0, 2).join(' · ')}
              </Text>
            </div>
            <Badge>{item.run.status}</Badge>
            <Button
              component={Link}
              to={`/catalog/runs/${item.run.id}`}
              variant="light"
            >
              View run
            </Button>
          </div>
        </Paper>
      ))}
      {data?.total === 0 && <Text>No matching runs yet.</Text>}
      {!!data && data.total > 24 && (
        <Group justify="center" py="xl"><Pagination
          total={Math.ceil(data.total / 24)}
          value={page}
          onChange={(next) =>
            setParams({ kind: 'runs', q: search, page: String(next) })
          }
        /></Group>
      )}
    </Stack>
  );
}

export function PublicRun() {
  const { runId } = useParams();
  const [detail, setDetail] = useState<RunInspection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    setDetail(null);
    setError(null);
    const load = async () => {
      try {
        const next = await inspectRun(runId ?? '');
        if (!disposed) {
          setDetail(next);
          if (['queued', 'running'].includes(next.run.status))
            timer = setTimeout(() => void load(), 2500);
        }
      } catch (cause) {
        if (!disposed) setError(message(cause));
      }
    };
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [runId, retry]);
  return (
    <CatalogFrame>
      <Button
        component={Link}
        to="/catalog?kind=runs"
        variant="subtle"
        w="fit-content"
      >
        Back to public runs
      </Button>
      {error && (
        <Alert color="red">
          {error}
          <Button onClick={() => setRetry((x) => x + 1)}>Try again</Button>
        </Alert>
      )}
      {!detail ? (
        !error && <Loader />
      ) : (
        <>
          <Group justify="space-between">
            <Title order={1}>{detail.run.name}</Title>
            <Badge>{detail.run.status}</Badge>
          </Group>
          {detail.run.error && (
            <Alert color="yellow">{detail.run.error.message}</Alert>
          )}
          {detail.availability.full_result && (
            <Button component={Link} to={`/catalog/runs/${runId}/playback`}>
              Open result playback
            </Button>
          )}
          <ResultDetails inspection={detail} />
        </>
      )}
    </CatalogFrame>
  );
}

export function PublicPlayback() {
  const { runId } = useParams();
  const [run, setRun] = useState<CompletedSimulationRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let disposed = false;
    void getSimulationResult(runId ?? '')
      .then((next) => {
        if (!disposed) setRun(next);
      })
      .catch((cause) => {
        if (!disposed) setError(message(cause));
      });
    return () => {
      disposed = true;
    };
  }, [runId]);
  return (
    <CatalogFrame>
      {error ? (
        <Alert color="red">{error}</Alert>
      ) : !run ? (
        <Loader aria-label="Loading playback" />
      ) : (
        <SimulationPlayback
          result={run.result}
          document={run.inputDocumentSnapshot}
          sceneGeometry={run.sceneGeometry}
          course={run.course}
          navigation={[{ label: 'Run details', to: `/catalog/runs/${runId}` }]}
        />
      )}
    </CatalogFrame>
  );
}
