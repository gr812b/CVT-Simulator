import { useState } from 'react';
import { Alert, Modal, Stack, Text } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { Link } from 'react-router-dom';
import {
  managePublications,
  type PublicationKind,
  type ManagedPublication,
} from './api';
import { message } from '../experiments/api';

export function PublishDialog({
  kind,
  objectId,
  disabled,
}: {
  kind: PublicationKind;
  objectId: string;
  disabled: boolean;
}) {
  const [opened, setOpened] = useState(false);
  const [items, setItems] = useState<ManagedPublication[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const open = async () => {
    setOpened(true);
    setBusy(true);
    setError(null);
    try {
      setItems(await managePublications(kind, objectId));
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button
        variant="light"
        disabledReason={
          disabled
            ? 'Save your changes and unarchive this item to open its public revisions.'
            : undefined
        }
        onClick={() => void open()}
      >
        Public revisions
      </Button>
      <Modal
        opened={opened}
        onClose={() => setOpened(false)}
        title="Public revisions"
      >
        <Stack>
          <Text size="sm">
            Each saved revision has a public link. The latest active revision
            appears in the library.
          </Text>
          {error && <Alert color="red">{error}</Alert>}
          {busy && <Text role="status">Loading revisions…</Text>}
          {items.map(({ item }) => (
            <Button
              key={item.id}
              component={Link}
              to={`/catalog/${item.id}`}
              variant="light"
            >
              Revision {item.revision_number} · {item.name}
            </Button>
          ))}
        </Stack>
      </Modal>
    </>
  );
}
