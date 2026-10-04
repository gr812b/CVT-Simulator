import { useState } from 'react';
import {
  Accordion,
  Alert,
  Code,
  Group,
  Pagination,
  Paper,
  ScrollArea,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { downloadBlob } from '@utils/download';
import {
  exportRun,
  formatMetric,
  getFrozenInput,
  type ExportKind,
  type RunInspection,
} from './api';
import { ResultChart } from './ResultChart';
import { message } from '../experiments/api';

const exports: { kind: ExportKind; label: string; full: boolean }[] = [
  { kind: 'input', label: 'Canonical input JSON', full: false },
  { kind: 'summary', label: 'Summary JSON', full: false },
  { kind: 'result', label: 'Full result JSON', full: true },
  { kind: 'csv', label: 'Full report CSV', full: true },
];

export function ResultDetails({ inspection }: { inspection: RunInspection }) {
  const { run, references, metrics, availability, warnings, transitions } =
    inspection;
  const [busy, setBusy] = useState<ExportKind | 'input-view' | null>(null);
  const [input, setInput] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [transitionPage, setTransitionPage] = useState(1);
  const download = async (kind: ExportKind) => {
    setBusy(kind);
    setError(null);
    try {
      downloadBlob(
        await exportRun(run.id, kind),
        `cinder-${run.id}-${kind}.${kind === 'csv' ? 'csv' : 'json'}`,
      );
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(null);
    }
  };
  const loadInput = async () => {
    setBusy('input-view');
    setError(null);
    try {
      setInput(
        JSON.stringify(
          (await getFrozenInput(run.id)).input_document_snapshot,
          null,
          2,
        ),
      );
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(null);
    }
  };
  return (
    <Stack>
      <Paper withBorder p="lg">
        <Stack>
          <Title order={2} size="h3">
            Frozen configuration
          </Title>
          {references.map((ref) => (
            <div key={ref.kind}>
              <Text size="xs" tt="uppercase" c="dimmed">
                {ref.kind}
              </Text>
              <Text>
                {ref.name}
                {ref.revision_number
                  ? ` · revision ${ref.revision_number}`
                  : ''}
                {ref.unsaved ? ' · temporary values included' : ''}
              </Text>
              {ref.revision_id && (
                <Text size="xs" c="dimmed" style={{ overflowWrap: 'anywhere' }}>
                  {ref.revision_id}
                </Text>
              )}
            </div>
          ))}
          <Group>
            {exports.map((item) => (
              <Button
                key={item.kind}
                variant="default"
                size="xs"
                loading={busy === item.kind}
                disabledReason={
                  busy !== null
                    ? 'Wait for the current download.'
                    : item.full && !availability.full_result
                      ? 'The full result is not available for this run.'
                      : undefined
                }
                onClick={() => void download(item.kind)}
              >
                {item.label}
              </Button>
            ))}
          </Group>
          <Text size="xs" c="dimmed">
            Exports preserve canonical units. Full result JSON includes every
            retained field; CSV contains every report column and row. Optional
            raw traces exist only if they were requested and retained.
          </Text>
          {error && (
            <Alert color="red" role="alert">
              {error}
            </Alert>
          )}
          <Accordion variant="separated">
            <Accordion.Item value="input">
              <Accordion.Control>Inspect canonical input</Accordion.Control>
              <Accordion.Panel>
                {input ? (
                  <ScrollArea h={350}>
                    <Code block>{input}</Code>
                  </ScrollArea>
                ) : (
                  <Button
                    variant="light"
                    loading={busy === 'input-view'}
                    onClick={() => void loadInput()}
                  >
                    Load frozen input
                  </Button>
                )}
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
        </Stack>
      </Paper>
      {availability.partial && (
        <Alert color="yellow" title="Partial result">
          The worker returned a result, but the simulation did not reach its
          requested final time. Reported metrics describe only the available
          trajectory. Termination:{' '}
          {inspection.termination_reason?.replace(/_/g, ' ') ?? 'unspecified'}.
        </Alert>
      )}
      {run.status === 'completed' && !availability.full_result && (
        <Alert color="yellow" title="Full result unavailable">
          This run’s full artifact is no longer available.{' '}
          {availability.preview
            ? 'The retained display preview, summary and frozen input remain available.'
            : 'Its retained summary and frozen input remain available.'}{' '}
          A rerun creates a separate result; it does not restore this original
          computation.
        </Alert>
      )}
      {(availability.preview || availability.full_result) && (
        <ResultChart key={run.id} inspection={inspection} />
      )}
      {metrics.length > 0 && (
        <Paper withBorder p="lg">
          <Stack>
            <Title order={2} size="h3">
              Solver metrics
            </Title>
            <Text size="sm" c="dimmed">
              Saved with the original result. These values are never
              recalculated from a reduced display preview.
            </Text>
            <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
              {metrics.slice(0, 6).map((metric) => (
                <div key={metric.key}>
                  <Text size="xs" c="dimmed">
                    {metric.label}
                  </Text>
                  <Text size="xl" fw={600}>
                    {formatMetric(metric)}
                  </Text>
                </div>
              ))}
            </SimpleGrid>
            {metrics.length > 6 && (
              <Accordion>
                <Accordion.Item value="metrics">
                  <Accordion.Control>All stored metrics</Accordion.Control>
                  <Accordion.Panel>
                    <Table>
                      <Table.Tbody>
                        {metrics.map((metric) => (
                          <Table.Tr key={metric.key}>
                            <Table.Td>{metric.label}</Table.Td>
                            <Table.Td>{formatMetric(metric)}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Accordion.Panel>
                </Accordion.Item>
              </Accordion>
            )}
          </Stack>
        </Paper>
      )}
      {run.status === 'completed' && (
        <Paper withBorder p="lg">
          <Stack>
            <Title order={2} size="h3">
              Warnings & transitions
            </Title>
            <Text size="sm">
              Termination:{' '}
              {inspection.termination_reason?.replace(/_/g, ' ') ??
                'not recorded'}
            </Text>
            {warnings.length ? (
              warnings.map((warning, index) => (
                <Alert key={index} color="yellow">
                  {warning}
                </Alert>
              ))
            ) : (
              <Text size="sm" c="dimmed">
                No solver warnings were recorded.
              </Text>
            )}
            {transitions.length ? (
              <>
                <Table.ScrollContainer minWidth={600}>
                  <Table striped>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Time (s)</Table.Th>
                        <Table.Th>Events</Table.Th>
                        <Table.Th>Reason</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {transitions
                        .slice((transitionPage - 1) * 25, transitionPage * 25)
                        .map((transition, index) => (
                          <Table.Tr key={`${transitionPage}/${index}`}>
                            <Table.Td>
                              {transition.time_s.toPrecision(6)}
                            </Table.Td>
                            <Table.Td>
                              {transition.events.join(', ')}
                              {transition.terminates ? ' · stops run' : ''}
                            </Table.Td>
                            <Table.Td>
                              {transition.reason.replace(/_/g, ' ')}
                            </Table.Td>
                          </Table.Tr>
                        ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
                {transitions.length > 25 && (
                  <Pagination
                    total={Math.ceil(transitions.length / 25)}
                    value={transitionPage}
                    onChange={setTransitionPage}
                  />
                )}
              </>
            ) : (
              <Text size="sm" c="dimmed">
                No transitions were recorded.
              </Text>
            )}
          </Stack>
        </Paper>
      )}
    </Stack>
  );
}
