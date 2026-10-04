import { useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Group,
  Modal,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core';
import { DifferenceList } from '../physicalLibrary/PhysicalStatus';
import {
  archiveExperiment,
  compareExperiments,
  message,
  restoreExperiment,
  type ExperimentDetail,
  type ExperimentDocument,
  type ExperimentItem,
} from './api';

export function RevisionToolbar({
  label,
  document,
  detail,
  items,
  busy,
  invalid,
  onChange,
  onLoad,
  onNew,
  onSave,
  onRestored,
  onRefresh,
}: {
  label: string;
  document: ExperimentDocument;
  detail: ExperimentDetail | null;
  items: ExperimentItem[];
  busy: boolean;
  invalid: boolean;
  onChange: (document: ExperimentDocument) => void;
  onLoad: (id: string) => void;
  onNew: () => void;
  onSave: (asNew: boolean) => void;
  onRestored: (detail: ExperimentDetail) => void;
  onRefresh: () => void;
}) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const [revision, setRevision] = useState<string | null>(null);
  const [differences, setDifferences] = useState<Awaited<
    ReturnType<typeof compareExperiments>
  > | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const dirty =
    !detail || JSON.stringify(document) !== JSON.stringify(detail.document);
  const task = async (action: () => Promise<void>) => {
    setWorking(true);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setWorking(false);
    }
  };
  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <Text fw={700} size="lg">
          {label}
        </Text>
        <Badge variant="light" color={dirty ? 'yellow' : 'teal'}>
          {dirty
            ? 'Unsaved values'
            : `Saved · revision ${detail!.item.revision_number}`}
        </Badge>
      </Group>
      <Select
        label={`Open saved ${label.toLowerCase()}`}
        placeholder="New working copy"
        searchable
        clearable
        value={detail?.item.id ?? null}
        data={items.map((item) => ({
          value: item.id,
          label: `${item.name} · r${item.revision_number}${item.owned ? '' : ' · sample'}${item.archived ? ' · archived' : ''}`,
        }))}
        disabled={busy || working}
        onChange={(id) => (id ? onLoad(id) : onNew())}
      />
      <TextInput
        label={`${label} name`}
        value={document.name}
        maxLength={240}
        required
        onChange={(event) =>
          onChange({ ...document, name: event.currentTarget.value })
        }
      />
      <Textarea
        label={`${label} notes`}
        value={document.notes ?? ''}
        maxLength={4000}
        autosize
        minRows={1}
        maxRows={4}
        onChange={(event) =>
          onChange({ ...document, notes: event.currentTarget.value })
        }
      />
      <Group gap="xs">
        <Button
          size="xs"
          variant="light"
          disabled={
            busy ||
            working ||
            invalid ||
            !document.name.trim() ||
            Boolean(detail?.item.archived)
          }
          onClick={() => onSave(false)}
        >
          {detail?.item.owned ? `Save ${label.toLowerCase()}` : 'Save as new'}
        </Button>
        <Button
          size="xs"
          variant="default"
          disabled={busy || working || invalid || !document.name.trim()}
          onClick={() => onSave(true)}
        >
          Save as / Duplicate
        </Button>
        <Button
          size="xs"
          variant="subtle"
          disabled={!detail || busy || working}
          onClick={() => {
            setHistoryOpen(true);
            setRevision(null);
            setDifferences(null);
            setError(null);
          }}
        >
          History
        </Button>
        {detail?.item.owned && (
          <Button
            size="xs"
            variant="subtle"
            disabled={busy || working}
            onClick={() =>
              void task(async () => {
                if (
                  dirty &&
                  !window.confirm(
                    'Discard the unsaved values and change this item’s archive status?',
                  )
                )
                  return;
                await archiveExperiment(detail);
                onRefresh();
                onRestored({
                  ...detail,
                  item: { ...detail.item, archived: !detail.item.archived },
                });
              })
            }
          >
            {detail.item.archived ? 'Unarchive' : 'Archive'}
          </Button>
        )}
      </Group>
      {detail?.item.archived && (
        <Alert color="yellow">
          Archived. Unarchive to save changes, or save a new copy.
        </Alert>
      )}
      {error && !historyOpen && (
        <Alert color="red" role="alert">
          {error}
        </Alert>
      )}
      <Modal
        opened={historyOpen}
        onClose={() => setHistoryOpen(false)}
        title={`${label} revision history`}
        size="lg"
      >
        <Stack>
          <Text size="sm">
            Revisions never change. Restore makes a new revision; it does not
            overwrite past runs.
          </Text>
          <Select
            label="Revision to compare with current"
            value={revision}
            data={
              detail?.history.map((item) => ({
                value: item.id,
                label: `Revision ${item.number} · ${item.name}`,
              })) ?? []
            }
            onChange={(id) => {
              setRevision(id);
              setDifferences(null);
              if (id && detail)
                void task(async () =>
                  setDifferences(
                    await compareExperiments(id, detail.item.revision_id),
                  ),
                );
            }}
          />
          {error && (
            <Alert color="red" role="alert">
              {error}
            </Alert>
          )}
          {differences && <DifferenceList differences={differences} />}
          <Button
            loading={working}
            disabled={
              !revision ||
              revision === detail?.item.revision_id ||
              !detail?.item.owned ||
              detail.item.archived
            }
            onClick={() => {
              if (!detail || !revision) return;
              if (
                dirty &&
                !window.confirm(
                  'Restore this revision and discard the current unsaved values?',
                )
              )
                return;
              void task(async () => {
                onRestored(await restoreExperiment(detail, revision));
                onRefresh();
                setHistoryOpen(false);
              });
            }}
          >
            Restore as new revision
          </Button>
        </Stack>
      </Modal>
    </Stack>
  );
}
