import { FormError } from '@components/form/FormError';
import { libraryOptions } from '../physicalLibrary/libraryOptions';
import { useState } from 'react';
import {
  Alert,
  Badge,
  Group,
  Modal,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
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
  showPicker = true,
  showFields = true,
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
  showPicker?: boolean;
  showFields?: boolean;
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
          {dirty ? 'Unsaved values' : 'Saved'}
        </Badge>
      </Group>
      {showPicker && (
        <Select
          label={`Open saved ${label.toLowerCase()}`}
          placeholder="New working copy"
          searchable
          clearable
          value={detail?.item.id ?? null}
          data={libraryOptions(items, (item) => item.id)}
          disabled={busy || working}
          onChange={(id) => (id ? onLoad(id) : onNew())}
        />
      )}
      {showFields && <>
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
      </>}
      <Group gap="xs">
        <Button
          size="md"
          variant="filled"
          disabledReason={
            busy || working
              ? 'Please wait for the current action.'
              : invalid
                ? 'Correct the highlighted inputs and road profile.'
                : !document.name.trim()
                  ? 'Enter a name.'
                  : detail?.item.archived
                    ? 'Unarchive this item before saving a revision.'
                    : undefined
          }
          onClick={() => onSave(false)}
        >
          {detail?.item.owned ? `Save ${label.toLowerCase()}` : `Save new ${label.toLowerCase()}`}
        </Button>
        <Button
          size="xs"
          variant="default"
          disabledReason={
            busy || working
              ? 'Please wait for the current action.'
              : invalid
                ? 'Correct the highlighted inputs and road profile.'
                : !document.name.trim()
                  ? 'Enter a name.'
                  : undefined
          }
          onClick={() => onSave(true)}
        >
          Save as / Duplicate
        </Button>
        <Button
          size="xs"
          variant="subtle"
          disabledReason={
            !detail
              ? 'Save this item to start its revision history.'
              : busy || working
                ? 'Please wait for the current action.'
                : undefined
          }
          onClick={() => {
            setHistoryOpen(true);
            setRevision(null);
            setDifferences(null);
            setError(null);
          }}
        >
          Version history
        </Button>
        {detail?.item.owned && (
          <Button
            size="xs"
            variant="subtle"
            disabledReason={
              busy || working
                ? 'Please wait for the current action.'
                : undefined
            }
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
        <FormError color="red" role="alert">
          {error}
        </FormError>
      )}
      <Modal
        opened={historyOpen}
        onClose={() => setHistoryOpen(false)}
        title={`${label} version history`}
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
            <FormError color="red" role="alert">
              {error}
            </FormError>
          )}
          {differences && <DifferenceList differences={differences} />}
          <Button
            loading={working}
            disabledReason={
              !revision
                ? 'Choose an earlier revision.'
                : revision === detail?.item.revision_id
                  ? 'This is already the current revision.'
                  : !detail?.item.owned
                    ? 'Make your own copy to restore earlier values.'
                    : detail.item.archived
                      ? 'Unarchive this item before restoring a revision.'
                      : undefined
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
