import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Accordion,
  Alert,
  Badge,
  Button,
  Container,
  Group,
  Loader,
  Modal,
  Paper,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core';
import {
  IconArrowLeft,
  IconCheck,
  IconCopy,
  IconHistory,
  IconPlayerPlay,
} from '@tabler/icons-react';
import {
  Link,
  Navigate,
  useBeforeUnload,
  useBlocker,
  useNavigate,
  useParams,
} from 'react-router-dom';
import { QuantityValidationContext } from '@components/quantityInput/validation';
import {
  archivePhysical,
  copyPhysical,
  getPhysical,
  kindLabels,
  listPhysical,
  physicalMetadata,
  physicalTemplate,
  previewUpdate,
  restorePhysical,
  savePhysical,
  singularLabels,
  validatePhysical,
  type PhysicalDetail,
  type PhysicalDocument,
  type PhysicalField,
  type PhysicalItem,
  type PhysicalKind,
  type PhysicalResolvedCase,
  type PhysicalUpdatePreview,
  type PhysicalValidation,
} from './api';
import { BeltEditor } from './BeltEditor';
import { ComponentPicker } from './ComponentPicker';
import { CvtEditor } from './CvtEditor';
import { EngineEditor } from './EngineEditor';
import { isPhysicalKind } from './api';
import { DifferenceList, PhysicalStatus } from './PhysicalStatus';
import { RevisionHistory } from './RevisionHistory';
import { VehicleEditor } from './VehicleEditor';
import styles from './PhysicalEditor.module.scss';
import { PublishDialog } from '../publicLibrary/PublishDialog';
import { CopyAttribution } from '../publicLibrary/CopyAttribution';

export function PhysicalEditorPage() {
  const { kind, objectId } = useParams();
  if (!isPhysicalKind(kind) || !objectId)
    return <Navigate to="/library/setups" replace />;
  return (
    <PhysicalEditor
      key={`${kind}/${objectId}`}
      kind={kind}
      objectId={objectId}
    />
  );
}

function PhysicalEditor({
  kind,
  objectId,
}: {
  kind: PhysicalKind;
  objectId: string;
}) {
  const navigate = useNavigate();
  const isNew = objectId === 'new';
  const [detail, setDetail] = useState<PhysicalDetail | null>(null);
  const [document, setDocument] = useState<PhysicalDocument | null>(null);
  const [saved, setSaved] = useState('');
  const [validated, setValidated] = useState('');
  const [validation, setValidation] = useState<PhysicalValidation | null>(null);
  const [resolved, setResolved] = useState<PhysicalResolvedCase | null>(null);
  const [fields, setFields] = useState<PhysicalField[]>([]);
  const [catalog, setCatalog] = useState<PhysicalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [workingBusy, setBusy] = useState(false);
  const [componentLoading, setComponentLoading] = useState(false);
  const busy = workingBusy || componentLoading;
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [note, setNote] = useState('');
  const [invalid, setInvalid] = useState(new Set<string>());
  const [historyOpen, setHistoryOpen] = useState(false);
  const [update, setUpdate] = useState<PhysicalUpdatePreview | null>(null);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [reloadOpen, setReloadOpen] = useState(false);
  const permitNavigation = useRef(false);
  const serialized = document ? JSON.stringify(document) : '';
  const dirty = !!document && (serialized !== saved || invalid.size > 0);
  const editable = isNew || !!detail?.item.owned;
  const blocker = useBlocker(
    useCallback(() => dirty && !permitNavigation.current, [dirty]),
  );
  useBeforeUnload(
    useCallback(
      (event) => {
        if (dirty) {
          event.preventDefault();
          event.returnValue = '';
        }
      },
      [dirty],
    ),
  );

  const accept = useCallback((next: PhysicalDetail) => {
    setDetail(next);
    setDocument(next.document);
    setSaved(JSON.stringify(next.document));
    setValidated(JSON.stringify(next.document));
    setValidation(next.validation);
    setResolved(null);
    setNote('');
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const load = async () => {
      try {
        const [loaded, metadata, engines, belts, cvts] = await Promise.all([
          isNew
            ? physicalTemplate(kind, controller.signal)
            : getPhysical(kind, objectId, undefined, controller.signal),
          physicalMetadata(controller.signal),
          listPhysical('engines', 'all', false, controller.signal),
          listPhysical('belts', 'all', false, controller.signal),
          listPhysical('cvts', 'all', false, controller.signal),
        ]);
        if (controller.signal.aborted) return;
        if ('document' in loaded) accept(loaded);
        else {
          setDocument(loaded);
          setSaved(JSON.stringify(loaded));
          setValidated('');
          setValidation(null);
        }
        setFields(metadata.cvt_fields);
        setCatalog([...engines, ...belts, ...cvts]);
      } catch (reason) {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : 'Unable to load this item.',
          );
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void load();
    return () => controller.abort();
  }, [kind, objectId, isNew, retry, accept]);

  const perform = async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await work();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to complete this action.',
      );
    } finally {
      setBusy(false);
    }
  };
  const save = () =>
    perform(async () => {
      if (!document || invalid.size) return;
      const result = await savePhysical(
        document,
        detail?.item.revision_id ?? null,
        isNew ? undefined : objectId,
        note,
      );
      accept(result.detail);
      setMessage(
        result.changed
          ? `Saved revision ${result.detail.item.revision_number}.`
          : 'Already saved. No duplicate revision was created.',
      );
      if (isNew) {
        permitNavigation.current = true;
        navigate(`/library/${kind}/${result.detail.item.id}`, {
          replace: true,
        });
      }
    });
  const check = () =>
    perform(async () => {
      if (!document || invalid.size) return;
      const result = await validatePhysical(document);
      setValidation(result.validation);
      setValidated(serialized);
      setResolved(result.resolved_simulation_case ?? null);
      setMessage(result.validation.is_valid ? 'Input check complete.' : null);
    });
  const duplicate = () =>
    perform(async () => {
      if (!detail) return;
      const result = await copyPhysical(kind, detail.item.revision_id);
      permitNavigation.current = true;
      navigate(`/library/${kind}/${result.item.id}`);
    });
  const restore = (revision: string) =>
    perform(async () => {
      if (!detail) return;
      const result = await restorePhysical(
        kind,
        objectId,
        revision,
        detail.item.revision_id,
      );
      accept(result.detail);
      setHistoryOpen(false);
      setMessage(`Restored as revision ${result.detail.item.revision_number}.`);
    });
  const applyUpdate = () =>
    perform(async () => {
      if (!update) return;
      const result = await savePhysical(
        update.document,
        update.expected_revision_id,
        objectId,
        'Explicitly applied a reviewed component update.',
      );
      accept(result.detail);
      setUpdate(null);
      setMessage(
        `Component update saved in revision ${result.detail.item.revision_number}.`,
      );
    });
  const archive = () =>
    perform(async () => {
      if (!detail) return;
      const item = await archivePhysical(detail.item, !detail.item.archived);
      setDetail({ ...detail, item });
      setArchiveOpen(false);
      setMessage(
        item.archived
          ? 'Archived. Its saved revisions remain available.'
          : 'Returned to your active library.',
      );
    });
  const downloadResolved = () => {
    if (!resolved) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(resolved, null, 2)], {
        type: 'application/json',
      }),
    );
    const link = window.document.createElement('a');
    link.href = url;
    link.download = 'cinder-physical-setup.json';
    link.click();
    URL.revokeObjectURL(url);
  };

  if (loading)
    return (
      <Container py="xl">
        <Group>
          <Loader size="sm" />
          <Text role="status">
            Loading physical inputs and checking the saved configuration…
          </Text>
        </Group>
      </Container>
    );
  if (!document)
    return (
      <Container py="xl">
        <Alert color="red" title="Item unavailable" role="alert">
          {error}
          <Button
            variant="subtle"
            onClick={() => setRetry((value) => value + 1)}
          >
            Try again
          </Button>
        </Alert>
      </Container>
    );
  const disabled = !editable || busy;
  const componentItems = (componentKind: PhysicalKind) =>
    catalog.filter((item) => item.kind === componentKind);
  return (
    <Container size="lg" py="lg">
      <Stack gap="lg">
        <Group justify="space-between">
          <Button
            component={Link}
            to={`/library/${kind}`}
            variant="subtle"
            leftSection={<IconArrowLeft size={16} />}
          >
            {kindLabels[kind]}
          </Button>
          <Group>
            <Badge variant="outline" color={dirty ? 'yellow' : 'teal'}>
              {dirty
                ? 'Unsaved changes'
                : isNew
                  ? 'New working copy'
                  : `Saved · revision ${detail?.item.revision_number}`}
            </Badge>
            {detail?.item.archived && <Badge color="gray">Archived</Badge>}
          </Group>
        </Group>
        <div>
          <Title order={1}>
            {isNew ? `New ${singularLabels[kind]}` : detail?.item.name}
          </Title>
          <Text c="dimmed" mt="xs">
            {kind === 'setups'
              ? 'One place for your vehicle, engine, belt and CVT. Save creates the necessary component revisions together.'
              : 'Reusable physical inputs with an immutable history.'}
          </Text>
        </div>
        {!editable && (
          <Alert color="blue" title="Sample revision">
            Explore these saved values, then copy them into your private library
            to edit.
          </Alert>
        )}
        {detail?.item.owned && (
          <CopyAttribution kind={kind} objectId={objectId} />
        )}
        {isNew && (
          <Alert color="blue" variant="light">
            The form starts with project example values. Replace them with your
            measurements and record their source before treating them as your
            hardware.
          </Alert>
        )}
        <QuantityValidationContext.Provider value={setInvalid}>
          <form
            className={styles.form}
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              if (!busy && editable) void save();
            }}
          >
            <Stack gap="lg">
              <div className={styles.actions}>
                <Group justify="space-between">
                  <Group gap="sm">
                    {editable && (
                      <Button
                        type="submit"
                        leftSection={<IconCheck size={16} />}
                        loading={busy}
                        disabled={invalid.size > 0 || !document.name.trim()}
                      >
                        Save
                      </Button>
                    )}
                    <Button
                      variant="default"
                      disabled={busy || invalid.size > 0}
                      onClick={() => void check()}
                    >
                      Check inputs
                    </Button>
                    {detail?.item.owned &&
                      (kind === 'setups' || kind === 'cvts') && (
                        <PublishDialog
                          kind={kind}
                          objectId={objectId}
                          disabled={busy || dirty || detail.item.archived}
                        />
                      )}
                    {detail && (
                      <Button
                        variant="default"
                        leftSection={<IconCopy size={16} />}
                        disabled={busy || dirty}
                        onClick={() => void duplicate()}
                      >
                        {editable ? 'Duplicate' : 'Copy to my library'}
                      </Button>
                    )}
                  </Group>
                  {detail && (
                    <Button
                      variant="subtle"
                      leftSection={<IconHistory size={16} />}
                      disabled={busy || dirty}
                      onClick={() => setHistoryOpen(true)}
                    >
                      History ({detail.history.length})
                    </Button>
                  )}
                </Group>
              </div>
              {busy && (
                <Text role="status" size="sm" c="dimmed">
                  Checking physical inputs and completing your action…
                </Text>
              )}
              {error && (
                <Alert
                  color="red"
                  title="Action could not be completed"
                  role="alert"
                >
                  {error}
                  {detail && (
                    <Button
                      variant="subtle"
                      size="xs"
                      onClick={() => setReloadOpen(true)}
                    >
                      Reload saved revision
                    </Button>
                  )}
                </Alert>
              )}
              {message && (
                <Alert color="teal" role="status">
                  {message}
                </Alert>
              )}
              <PhysicalStatus
                validation={validation}
                stale={serialized !== validated || invalid.size > 0}
                setup={kind === 'setups'}
              />
              {resolved && serialized === validated && (
                <Button variant="subtle" onClick={downloadResolved}>
                  Download resolved CINDER input
                </Button>
              )}
              {!!detail?.updates.length && (
                <Alert color="blue" title="Component updates available">
                  <Stack gap="sm">
                    <Text size="sm">
                      This configuration still uses its saved revisions. Review
                      the differences before applying an update.
                    </Text>
                    {detail.updates.map((item) => (
                      <Group key={item.component} justify="space-between">
                        <Text size="sm">
                          {item.name}: r{item.current_number} → r
                          {item.available_number}
                        </Text>
                        <Button
                          size="xs"
                          variant="light"
                          disabled={busy || dirty || !editable}
                          onClick={() =>
                            void perform(async () =>
                              setUpdate(
                                await previewUpdate(kind, objectId, item),
                              ),
                            )
                          }
                        >
                          Review {item.component} update
                        </Button>
                      </Group>
                    ))}
                  </Stack>
                </Alert>
              )}
              <fieldset className={styles.working} disabled={busy}>
                <Stack gap="lg">
                  <Paper withBorder p="lg">
                    <Stack>
                      <TextInput
                        label="Name"
                        value={document.name}
                        required
                        maxLength={240}
                        disabled={disabled}
                        onChange={(event) =>
                          setDocument({
                            ...document,
                            name: event.currentTarget.value,
                          })
                        }
                      />
                      <Textarea
                        label="Description"
                        value={document.description ?? ''}
                        autosize
                        minRows={2}
                        maxLength={4000}
                        disabled={disabled}
                        onChange={(event) =>
                          setDocument({
                            ...document,
                            description: event.currentTarget.value,
                          })
                        }
                      />
                    </Stack>
                  </Paper>
                  <Paper withBorder p="lg">
                    {document.kind === 'engines' && (
                      <EngineEditor
                        value={document.data}
                        onChange={(data) => setDocument({ ...document, data })}
                        disabled={disabled}
                      />
                    )}
                    {document.kind === 'belts' && (
                      <BeltEditor
                        value={document.data}
                        onChange={(data) => setDocument({ ...document, data })}
                        disabled={disabled}
                      />
                    )}
                    {document.kind === 'cvts' && (
                      <CvtEditor
                        value={document.data}
                        onChange={(data) => setDocument({ ...document, data })}
                        fields={fields}
                        belts={componentItems('belts')}
                        disabled={disabled}
                        onLoadingChange={setComponentLoading}
                      />
                    )}
                    {document.kind === 'setups' && (
                      <Accordion
                        multiple
                        defaultValue={['vehicle']}
                        variant="separated"
                      >
                        <Accordion.Item value="vehicle">
                          <Accordion.Control>
                            Vehicle & drivetrain
                          </Accordion.Control>
                          <Accordion.Panel>
                            <VehicleEditor
                              value={document.data.vehicle}
                              onChange={(vehicle) =>
                                setDocument({
                                  ...document,
                                  data: { ...document.data, vehicle },
                                })
                              }
                              disabled={disabled}
                            />
                          </Accordion.Panel>
                        </Accordion.Item>
                        <Accordion.Item value="engine">
                          <Accordion.Control>
                            Engine · {document.data.engine.name}
                          </Accordion.Control>
                          <Accordion.Panel>
                            <Stack>
                              <ComponentPicker
                                kind="engines"
                                value={document.data.engine}
                                onChange={(engine) =>
                                  setDocument({
                                    ...document,
                                    data: { ...document.data, engine },
                                  })
                                }
                                items={componentItems('engines')}
                                disabled={disabled}
                                onLoadingChange={setComponentLoading}
                              />
                              <EngineEditor
                                value={document.data.engine.data}
                                onChange={(data) =>
                                  setDocument({
                                    ...document,
                                    data: {
                                      ...document.data,
                                      engine: { ...document.data.engine, data },
                                    },
                                  })
                                }
                                disabled={disabled}
                              />
                            </Stack>
                          </Accordion.Panel>
                        </Accordion.Item>
                        <Accordion.Item value="cvt">
                          <Accordion.Control>
                            CVT & belt · {document.data.cvt.name}
                          </Accordion.Control>
                          <Accordion.Panel>
                            <Stack>
                              <ComponentPicker
                                kind="cvts"
                                value={document.data.cvt}
                                onChange={(cvt) =>
                                  setDocument({
                                    ...document,
                                    data: { ...document.data, cvt },
                                  })
                                }
                                items={componentItems('cvts')}
                                disabled={disabled}
                                onLoadingChange={setComponentLoading}
                              />
                              <CvtEditor
                                value={document.data.cvt.data}
                                onChange={(data) =>
                                  setDocument({
                                    ...document,
                                    data: {
                                      ...document.data,
                                      cvt: { ...document.data.cvt, data },
                                    },
                                  })
                                }
                                fields={fields}
                                belts={componentItems('belts')}
                                disabled={disabled}
                                onLoadingChange={setComponentLoading}
                              />
                            </Stack>
                          </Accordion.Panel>
                        </Accordion.Item>
                      </Accordion>
                    )}
                  </Paper>
                  <Accordion variant="separated">
                    <Accordion.Item value="source">
                      <Accordion.Control>
                        Source & measurement notes
                      </Accordion.Control>
                      <Accordion.Panel>
                        <Stack>
                          <TextInput
                            label="Source or manufacturer"
                            value={document.source_label ?? ''}
                            maxLength={240}
                            disabled={disabled}
                            onChange={(event) =>
                              setDocument({
                                ...document,
                                source_label: event.currentTarget.value,
                              })
                            }
                          />
                          <TextInput
                            label="Source URL"
                            value={document.source_url ?? ''}
                            maxLength={500}
                            disabled={disabled}
                            onChange={(event) =>
                              setDocument({
                                ...document,
                                source_url: event.currentTarget.value,
                              })
                            }
                          />
                          <Textarea
                            label="Private measurement notes"
                            value={document.source_notes ?? ''}
                            autosize
                            minRows={3}
                            maxLength={4000}
                            disabled={disabled}
                            description="Record measurement method, dimensions or uncertainty, and any illustrative assumptions."
                            onChange={(event) =>
                              setDocument({
                                ...document,
                                source_notes: event.currentTarget.value,
                              })
                            }
                          />
                        </Stack>
                      </Accordion.Panel>
                    </Accordion.Item>
                  </Accordion>
                </Stack>
              </fieldset>
              {editable && (
                <Textarea
                  label="Note for this revision"
                  placeholder="What changed and why?"
                  value={note}
                  disabled={busy}
                  maxLength={2000}
                  onChange={(event) => setNote(event.currentTarget.value)}
                />
              )}
              <Group justify="space-between">
                {detail?.item.owned && (
                  <Button
                    variant="subtle"
                    color="gray"
                    disabled={busy || dirty}
                    onClick={() => setArchiveOpen(true)}
                  >
                    {detail.item.archived ? 'Unarchive' : 'Archive'}
                  </Button>
                )}
                {detail && kind === 'setups' && (
                  <Button
                    component={Link}
                    to={`/input?setup=${detail.item.id}`}
                    leftSection={<IconPlayerPlay size={16} />}
                    disabled={
                      busy ||
                      dirty ||
                      detail.item.archived ||
                      !detail.validation.is_valid
                    }
                  >
                    Tune & run this setup
                  </Button>
                )}
              </Group>
            </Stack>
          </form>
        </QuantityValidationContext.Provider>
        {detail && (
          <RevisionHistory
            detail={detail}
            opened={historyOpen}
            onClose={() => !busy && setHistoryOpen(false)}
            onRestore={restore}
            busy={busy}
          />
        )}
        <Modal
          opened={!!update}
          onClose={() => !busy && setUpdate(null)}
          title="Review component update"
          size="lg"
        >
          {update && (
            <Stack>
              <Text size="sm">
                Applying this update creates the necessary component and setup
                revisions. Existing runs and other setups stay unchanged.
              </Text>
              <PhysicalStatus
                validation={update.validation}
                setup={kind === 'setups'}
              />
              <Text size="xs" c="dimmed">
                Differences use canonical units: metres, radians, kilograms and
                seconds.
              </Text>
              <DifferenceList differences={update.differences} />
              <Group justify="end">
                <Button
                  variant="default"
                  disabled={busy}
                  onClick={() => setUpdate(null)}
                >
                  Keep current revision
                </Button>
                <Button loading={busy} onClick={() => void applyUpdate()}>
                  Apply update & save
                </Button>
              </Group>
            </Stack>
          )}
        </Modal>
        <Modal
          opened={archiveOpen}
          onClose={() => !busy && setArchiveOpen(false)}
          title={
            detail?.item.archived
              ? 'Unarchive this item?'
              : 'Archive this item?'
          }
        >
          <Stack>
            <Text>
              Archiving hides it from the active library. Existing setups and
              saved revisions remain available.
            </Text>
            <Group justify="end">
              <Button variant="default" onClick={() => setArchiveOpen(false)}>
                Cancel
              </Button>
              <Button loading={busy} onClick={() => void archive()}>
                {detail?.item.archived ? 'Unarchive' : 'Archive'}
              </Button>
            </Group>
          </Stack>
        </Modal>
        <Modal
          opened={reloadOpen}
          onClose={() => setReloadOpen(false)}
          title="Reload saved values?"
        >
          <Stack>
            <Text>
              This discards your working changes and opens the latest saved
              revision.
            </Text>
            <Group justify="end">
              <Button variant="default" onClick={() => setReloadOpen(false)}>
                Keep editing
              </Button>
              <Button
                onClick={() => {
                  setReloadOpen(false);
                  setRetry((value) => value + 1);
                }}
              >
                Discard & reload
              </Button>
            </Group>
          </Stack>
        </Modal>
        <Modal
          opened={blocker.state === 'blocked'}
          onClose={() => blocker.state === 'blocked' && blocker.reset()}
          title="Leave unsaved changes?"
        >
          <Stack>
            <Text>Your working values have not been saved.</Text>
            <Group justify="end">
              <Button
                variant="default"
                onClick={() => blocker.state === 'blocked' && blocker.reset()}
              >
                Keep editing
              </Button>
              <Button
                color="red"
                onClick={() => blocker.state === 'blocked' && blocker.proceed()}
              >
                Discard & leave
              </Button>
            </Group>
          </Stack>
        </Modal>
      </Stack>
    </Container>
  );
}
