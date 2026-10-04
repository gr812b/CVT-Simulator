import { useEffect, useState } from 'react';
import {
  Accordion,
  Alert,
  Button,
  Checkbox,
  Code,
  Group,
  Loader,
  Modal,
  Paper,
  Radio,
  ScrollArea,
  Select,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { Link } from 'react-router-dom';
import {
  changePublicationAccess,
  managePublications,
  previewPublication,
  publish,
  type ManagedPublication,
  type PublicationKind,
  type PublicationPreview,
  type PublishRequest,
} from './api';
import { PhysicalStatus } from '../physicalLibrary/PhysicalStatus';
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
  const [preview, setPreview] = useState<PublicationPreview | null>(null);
  const [publications, setPublications] = useState<ManagedPublication[]>([]);
  const [audience, setAudience] =
    useState<PublishRequest['visibility']>('unlisted');
  const [listed, setListed] = useState(true);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!opened) return;
    let disposed = false;
    setPreview(null);
    setError(null);
    setConsent(false);
    void Promise.all([
      previewPublication(kind, objectId),
      managePublications(kind, objectId),
    ])
      .then(([next, rows]) => {
        if (!disposed) {
          setPreview(next);
          setPublications(rows);
        }
      })
      .catch((cause) => {
        if (!disposed) setError(message(cause));
      });
    return () => {
      disposed = true;
    };
  }, [kind, objectId, opened, retry]);
  const doPublish = async () => {
    if (!preview || !consent) return;
    setBusy(true);
    setError(null);
    try {
      await publish(kind, objectId, {
        expected_revision_id: preview.source_revision_id,
        snapshot_hash: preview.snapshot_hash,
        visibility: audience,
        gallery_listed: audience === 'public' && listed,
        share_dependencies: true,
      });
      setPublications(await managePublications(kind, objectId));
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  };
  const already =
    preview &&
    publications.find(
      (row) => row.item.revision_number === preview.source_revision_number,
    );
  return (
    <>
      <Button
        variant="light"
        disabled={disabled}
        onClick={() => setOpened(true)}
      >
        Publish & sharing
      </Button>
      <Modal
        opened={opened}
        onClose={() => !busy && setOpened(false)}
        title="Publish a fixed configuration"
        size="lg"
      >
        <Stack>
          <Text size="sm">
            Publishing shares a snapshot of one saved revision, including the
            required component values. Your private item, other revisions and
            private measurement notes stay private.
          </Text>
          {error && (
            <Alert color="red" role="alert">
              {error}
              <Button
                variant="subtle"
                onClick={() => setRetry((value) => value + 1)}
              >
                Reload publication preview
              </Button>
            </Alert>
          )}
          {!preview ? (
            !error && <Loader aria-label="Preparing publication preview" />
          ) : (
            <>
              <Text fw={600}>
                {preview.document.name} · revision{' '}
                {preview.source_revision_number}
              </Text>
              <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                {preview.document.description ||
                  'No public description supplied. You can add one in the physical editor before publishing.'}
              </Text>
              <PhysicalStatus
                validation={preview.validation}
                setup={kind === 'setups'}
              />
              <Paper withBorder p="md">
                <Stack gap="xs">
                  <Text fw={600} size="sm">
                    Values included in the snapshot
                  </Text>
                  {preview.dependencies.map((dependency, index) => (
                    <Text key={index} size="sm">
                      {dependency.name}
                      {dependency.revision_number
                        ? ` · r${dependency.revision_number}`
                        : ''}{' '}
                      ·{' '}
                      {dependency.owned
                        ? 'from your library'
                        : 'from a shared source'}
                    </Text>
                  ))}
                </Stack>
              </Paper>
              <Accordion>
                <Accordion.Item value="snapshot">
                  <Accordion.Control>
                    Review the exact public configuration
                  </Accordion.Control>
                  <Accordion.Panel>
                    <ScrollArea h={300}>
                      <Code block>
                        {JSON.stringify(preview.document, null, 2)}
                      </Code>
                    </ScrollArea>
                  </Accordion.Panel>
                </Accordion.Item>
              </Accordion>
              {already ? (
                <Alert color="teal">
                  This saved revision already has a publication. Manage its
                  access below; save a changed revision to publish new values.
                </Alert>
              ) : (
                <>
                  <Radio.Group
                    label="Who can find this publication?"
                    value={audience}
                    onChange={(value) =>
                      setAudience(value === 'public' ? 'public' : 'unlisted')
                    }
                  >
                    <Stack mt="xs">
                      <Radio
                        value="unlisted"
                        label="Anyone with the link · unlisted"
                      />
                      <Radio value="public" label="Public publication" />
                    </Stack>
                  </Radio.Group>
                  {audience === 'public' && (
                    <Checkbox
                      label="List in the public library"
                      checked={listed}
                      onChange={(event) =>
                        setListed(event.currentTarget.checked)
                      }
                    />
                  )}
                  <Checkbox
                    label="I choose to share the included configuration and component values"
                    checked={consent}
                    onChange={(event) =>
                      setConsent(event.currentTarget.checked)
                    }
                  />
                  <Button
                    loading={busy}
                    disabled={!consent || !preview.validation.is_valid}
                    onClick={() => void doPublish()}
                  >
                    Publish revision {preview.source_revision_number}
                  </Button>
                </>
              )}
              {publications.map((row) => (
                <PublicationAccess
                  key={`${row.item.id}/${row.access_version}`}
                  value={row}
                  onChange={(updated) =>
                    setPublications((current) =>
                      current.map((item) =>
                        item.item.id === updated.item.id ? updated : item,
                      ),
                    )
                  }
                />
              ))}
            </>
          )}
        </Stack>
      </Modal>
    </>
  );
}

function PublicationAccess({
  value,
  onChange,
}: {
  value: ManagedPublication;
  onChange: (value: ManagedPublication) => void;
}) {
  const initial =
    value.item.visibility === 'private'
      ? 'private'
      : value.item.visibility === 'unlisted'
        ? 'unlisted'
        : value.item.gallery_listed
          ? 'listed'
          : 'public';
  const [access, setAccess] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      onChange(
        await changePublicationAccess(value.item.id, {
          expected_access_version: value.access_version,
          visibility:
            access === 'listed'
              ? 'public'
              : (access as ManagedPublication['item']['visibility']),
          gallery_listed: access === 'listed',
        }),
      );
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
      setConfirm(false);
    }
  };
  return (
    <Paper withBorder p="md">
      <Stack gap="sm">
        <Text fw={600}>
          Publication {value.item.publication_number} · source r
          {value.item.revision_number}
        </Text>
        {value.item.visibility !== 'private' && (
          <>
            <TextInput
              label="Share link"
              value={`${window.location.origin}/catalog/${value.item.id}`}
              readOnly
              onFocus={(event) => event.currentTarget.select()}
            />
            <Button
              component={Link}
              to={`/catalog/${value.item.id}`}
              variant="subtle"
            >
              View publication
            </Button>
          </>
        )}
        <Select
          label={`Access for publication ${value.item.publication_number}`}
          value={access}
          onChange={(next) => next && setAccess(next)}
          data={[
            { value: 'listed', label: 'Public · listed in library' },
            { value: 'public', label: 'Public · link only' },
            { value: 'unlisted', label: 'Unlisted · link only' },
            { value: 'private', label: 'Withdrawn · private' },
          ]}
        />
        <Button
          variant="default"
          disabled={access === initial}
          loading={busy}
          onClick={() =>
            access === 'private' ? setConfirm(true) : void save()
          }
        >
          Save sharing
        </Button>
        {error && <Alert color="red">{error}</Alert>}
        {confirm && (
          <Alert color="yellow" title="Withdraw this publication?">
            <Text size="sm">
              Its public page and new copies will be unavailable. Previously
              copied configurations remain with their owners.
            </Text>
            <Group mt="sm">
              <Button loading={busy} color="red" onClick={() => void save()}>
                Withdraw publication
              </Button>
              <Button variant="default" onClick={() => setConfirm(false)}>
                Keep shared
              </Button>
            </Group>
          </Alert>
        )}
      </Stack>
    </Paper>
  );
}
