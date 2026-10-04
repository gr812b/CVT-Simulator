import { useEffect, useState } from 'react';
import {
  Alert,
  Group,
  Loader,
  Modal,
  Select,
  Stack,
  Text,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import {
  comparePhysical,
  type PhysicalDetail,
  type PhysicalDifference,
} from './api';
import { DifferenceList } from './PhysicalStatus';

export function RevisionHistory({
  detail,
  opened,
  onClose,
  onRestore,
  busy,
}: {
  detail: PhysicalDetail;
  opened: boolean;
  onClose: () => void;
  onRestore: (revision: string) => Promise<void>;
  busy: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [changes, setChanges] = useState<PhysicalDifference[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!opened) return;
    setSelected(
      detail.history.find((revision) => revision.id !== detail.item.revision_id)
        ?.id ?? detail.item.revision_id,
    );
  }, [opened, detail.history, detail.item.revision_id]);
  useEffect(() => {
    if (!opened || !selected) return;
    let active = true;
    setLoading(true);
    setError(null);
    comparePhysical(
      detail.item.kind,
      detail.item.id,
      detail.item.revision_id,
      selected,
    )
      .then((result) => {
        if (active) setChanges(result);
      })
      .catch((reason) => {
        if (active)
          setError(
            reason instanceof Error
              ? reason.message
              : 'Unable to compare revisions.',
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [opened, selected, detail.item]);
  const revision = detail.history.find((item) => item.id === selected);
  return (
    <Modal opened={opened} onClose={onClose} title="Revision history" size="lg">
      <Stack>
        <Text size="sm">
          Saved values are immutable. Restoring old values creates a new current
          revision and keeps the intervening history.
        </Text>
        <Select
          label="Saved revision"
          value={selected}
          allowDeselect={false}
          onChange={setSelected}
          disabled={busy}
          data={detail.history.map((item) => ({
            value: item.id,
            label: `Revision ${item.number} · ${new Date(item.created_at).toLocaleString()}${item.id === detail.item.revision_id ? ' · current' : ''}`,
          }))}
        />
        {revision && <Text size="sm">{revision.change_note}</Text>}
        <Text fw={600} size="sm">
          Current values → selected revision
        </Text>
        <Text size="xs" c="dimmed">
          Differences use canonical units: metres, radians, kilograms and
          seconds.
        </Text>
        {loading ? (
          <Group>
            <Loader size="sm" />
            <Text role="status">Comparing revisions…</Text>
          </Group>
        ) : error ? (
          <Alert color="red" role="alert">
            {error}
          </Alert>
        ) : (
          <DifferenceList differences={changes} />
        )}
        <Group justify="end">
          <Button
            variant="default"
            onClick={onClose}
            disabledReason={
              busy ? 'Wait for the revision to finish restoring.' : undefined
            }
          >
            Close
          </Button>
          {detail.item.owned && (
            <Button
              loading={busy}
              disabledReason={
                loading
                  ? 'Wait for the revision comparison.'
                  : error
                    ? 'Resolve the comparison error before restoring.'
                    : !selected
                      ? 'Select a saved revision to restore.'
                      : selected === detail.item.revision_id
                        ? 'This revision is already current.'
                        : undefined
              }
              onClick={() => selected && void onRestore(selected)}
            >
              Restore as new revision
            </Button>
          )}
        </Group>
      </Stack>
    </Modal>
  );
}
