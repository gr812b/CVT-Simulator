import { AuthorLink } from '../community/AuthorLink';
import { useAuth } from '@contexts/AuthContext';
import { ConfigurationView } from '../publicLibrary/ConfigurationView';
import { FormError } from '@components/form/FormError';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Modal } from '@components/modal/Modal';
import {
  Accordion,
  Alert,
  Badge,
  Container,
  Group,
  Loader,
  Paper,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import {
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
  useLocation,
  useParams,
  useSearchParams,
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
import { useEditorHistory } from '@components/editorHistory/useEditorHistory';
import { EditorHistoryBoundary, UndoRedoControls } from '@components/editorHistory/EditorHistory';
import type { DraftHistory } from '@components/editorHistory/draftHistory';
import { CvtTunes } from '../experiments/CvtTunes';
import { ConfigurationBack } from './ConfigurationLink';
import { PublishDialog } from '../publicLibrary/PublishDialog';
import { CopyAttribution } from '../publicLibrary/CopyAttribution';

export function PhysicalEditorPage() {
  const { kind, objectId } = useParams();
  const [params] = useSearchParams();
  const { session } = useAuth();
  // One-use, page-local handoff across the new-item URL change after its first save.
  // It is neither serialized into browser history nor shared between accounts.
  const handoff = useRef<{ key: string; user: string; history: DraftHistory<PhysicalDocument | null> } | null>(null);
  const routeKey = `${kind}/${objectId}/${params.get('revision') ?? ''}`;
  const owner = session?.user.id ?? '';
  const retained = handoff.current?.key === routeKey && handoff.current.user === owner
    ? handoff.current.history : undefined;
  useEffect(() => {
    if (handoff.current && (handoff.current.key !== routeKey || handoff.current.user !== owner))
      handoff.current = null;
  }, [routeKey, owner]);
  if (!isPhysicalKind(kind) || !objectId)
    return <Navigate to="/library/setups" replace />;
  return (
    <PhysicalEditor
      key={`${routeKey}/${owner}`}
      kind={kind}
      objectId={objectId}
      retainedHistory={retained}
      onCreated={(id, history) => { handoff.current = { key: `${kind}/${id}/`, user: owner, history }; }}
    />
  );
}

function PhysicalEditor({
  kind,
  objectId,
  retainedHistory,
  onCreated,
}: {
  kind: PhysicalKind;
  objectId: string;
  retainedHistory?: DraftHistory<PhysicalDocument | null>;
  onCreated: (id: string, history: DraftHistory<PhysicalDocument | null>) => void;
}) {
  const navigate = useNavigate();
  const { hash, state: returnState } = useLocation();
  const { session } = useAuth();
  const [params] = useSearchParams();
  const revisionId = params.get('revision') ?? undefined;
  const isNew = objectId === 'new';
  const [editing, setEditing] = useState(isNew);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [detail, setDetail] = useState<PhysicalDetail | null>(null);
  const draft = useEditorHistory<PhysicalDocument | null>(null, retainedHistory);
  const { history: editHistory, value: document, setValue: setDocument } = draft;
  const retainedOnLoad = useRef(Boolean(retainedHistory));
  const [validated, setValidated] = useState('');
  const [validation, setValidation] = useState<PhysicalValidation | null>(null);
  const [resolved, setResolved] = useState<PhysicalResolvedCase | null>(null);
  const [fields, setFields] = useState<PhysicalField[]>([]);
  const [catalog, setCatalog] = useState<PhysicalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [workingBusy, setBusy] = useState(false);
  const [componentLoading, setComponentLoading] = useState(false);
  const [componentSaveBlock, setComponentSaveBlock] = useState<string | null>(null);
  const busy = workingBusy || componentLoading || catalogLoading;
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [note, setNote] = useState('');
  const [invalid, setInvalid] = useState(new Set<string>());
  const [historyOpen, setHistoryOpen] = useState(false);
  const [update, setUpdate] = useState<PhysicalUpdatePreview | null>(null);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [reloadOpen, setReloadOpen] = useState(false);
  const [discardOpen, setDiscardOpen] = useState(false);
  const permitNavigation = useRef(false);
  const serialized = document ? JSON.stringify(document) : '';
  const dirty =
    !!document &&
    (draft.dirty || invalid.size > 0);
  const editable = editing && (isNew || !!detail?.item.owned);
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

  const accept = useCallback((next: PhysicalDetail, preserveHistory = false) => {
    setDetail(next);
    if (preserveHistory) editHistory.markSaved(next.document);
    else editHistory.reset(next.document);
    setValidated(JSON.stringify(next.document));
    setValidation(next.validation);
    setResolved(null);
    setNote('');
    setInvalid(new Set());
  }, [editHistory]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const load = async () => {
      try {
        const [loaded, metadata] = await Promise.all([
          isNew
            ? physicalTemplate(kind, controller.signal)
            : getPhysical(kind, objectId, revisionId, controller.signal),
          kind === 'cvts' || kind === 'setups'
            ? physicalMetadata(controller.signal)
            : Promise.resolve({ cvt_fields: [] }),
        ]);
        if (controller.signal.aborted) return;
        if ('document' in loaded) {
          accept(loaded, retainedOnLoad.current);
          retainedOnLoad.current = false;
        }
        else {
          const blank = { ...loaded, name: '' };
          editHistory.reset(blank);
          setValidated('');
          setValidation(null);
        }
        setFields(metadata.cvt_fields);
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
  }, [kind, objectId, revisionId, isNew, retry, accept, editHistory]);
  useEffect(() => {
    if (!loading && hash === '#tunes')
      window.document
        .getElementById('tunes')
        ?.scrollIntoView({ block: 'start' });
  }, [loading, hash]);
  useEffect(() => {
    if (!editable) return;
    const controller = new AbortController();
    setCatalogLoading(true);
    const kinds: PhysicalKind[] =
      kind === 'setups'
        ? ['engines', 'belts', 'cvts']
        : kind === 'cvts'
          ? ['belts']
          : [];
    void Promise.all(
      kinds.map((value) =>
        listPhysical(value, 'all', false, controller.signal),
      ),
    )
      .then((lists) => {
        if (!controller.signal.aborted) setCatalog(lists.flat());
      })
      .catch((cause) => {
        if (!controller.signal.aborted)
          setError(cause instanceof Error ? cause.message : String(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setCatalogLoading(false);
      });
    return () => controller.abort();
  }, [editable, kind]);

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
      if (!document || invalid.size || editHistory.getSnapshot().invalidCount || componentSaveBlock) return;
      const result = await savePhysical(
        document,
        detail?.item.revision_id ?? null,
        isNew ? undefined : objectId,
        note,
      );
      accept(result.detail, true);
      setEditing(false);
      setMessage(result.changed ? 'Saved.' : 'Already saved.');
      if (isNew) {
        onCreated(result.detail.item.id, editHistory);
        permitNavigation.current = true;
        navigate(`/library/${kind}/${result.detail.item.id}`, {
          state: returnState,
          replace: true,
        });
      }
    });
  const check = () =>
    perform(async () => {
      if (!document || invalid.size || editHistory.getSnapshot().invalidCount || componentSaveBlock) return;
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
      navigate(`/library/${kind}/${result.item.id}`, { state: returnState });
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
  const discardCurrentDraft = () => {
    setDiscardOpen(false);
    setError(null);
    setInvalid(new Set());
    if (isNew) {
      permitNavigation.current = true;
      navigate(`/library/${kind}`, { state: returnState, replace: true });
      return;
    }
    if (detail) accept(detail);
    setEditing(false);
  };
  const requestDiscardCurrentDraft = () => {
    if (dirty) {
      setDiscardOpen(true);
      return;
    }
    discardCurrentDraft();
  };

  if (isNew && !session)
    return (
      <Navigate
        to={`/login?next=${encodeURIComponent(`/library/${kind}/new`)}`}
        replace
      />
    );
  if (loading)
    return (
      <Container py="xl">
        <Group>
          <Loader size="sm" />
          <Text role="status">Loading configuration…</Text>
        </Group>
      </Container>
    );
  if (!document)
    return (
      <Container py="xl">
        <FormError color="red" title="Item unavailable" role="alert">
          {error}
          <Button
            variant="subtle"
            onClick={() => setRetry((value) => value + 1)}
          >
            Try again
          </Button>
        </FormError>
      </Container>
    );
  const disabled = !editable || busy;
  const restoreDraft = () => {
    setEditing(true);
    setMessage(null);
  };
  const invalidInputs = invalid.size + draft.invalidCount;
  const componentItems = (componentKind: PhysicalKind) =>
    catalog.filter((item) => item.kind === componentKind);
  return (
    <EditorHistoryBoundary history={editHistory}
      disabled={busy || (!isNew && (!detail?.item.owned || Boolean(revisionId)))} onRestore={restoreDraft}>
    <Container size="lg" py="lg">
      <Stack gap="lg">
        <Group justify="space-between">
          <ConfigurationBack
            to={session ? `/library/${kind}` : `/catalog?kind=${kind}`}
            label={kindLabels[kind]}
          />
          <Group>
            <Badge variant="outline" color={dirty ? 'yellow' : 'teal'}>
              {dirty ? 'Unsaved changes' : isNew ? 'New working copy' : 'Saved'}
            </Badge>
            {detail?.item.archived && <Badge color="gray">Archived</Badge>}
          </Group>
        </Group>
        <div>
          <Title order={1}>
            {isNew ? `New ${singularLabels[kind]}` : detail?.item.name}
          </Title>
          <Text c="dimmed" mt="xs">
            {document.description}
          </Text>
        </div>
        {!detail?.item.owned && !isNew && (
          <Alert
            color="blue"
            title={detail?.item.sample ? 'CINDER default' : 'Community item'}
          >
            Explore these saved values, then copy them into your library to
            edit.
          </Alert>
        )}
        {detail && (
          <Text size="sm" c="dimmed">
            By{' '}
            <AuthorLink name={detail.item.author} id={detail.item.author_id} />{' '}
            · v{detail.item.revision_number}
          </Text>
        )}
        {detail?.item.owned && (
          <CopyAttribution kind={kind} objectId={objectId} />
        )}
        {isNew && (
          <Alert color="blue" variant="light">
            The form starts with project example values. Replace them with your
            measurements for your hardware.
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
                    {(isNew || (detail?.item.owned && !revisionId)) && (
                      <UndoRedoControls history={editHistory} disabled={busy} onRestore={restoreDraft} />
                    )}
                    {detail?.item.owned && !editing && !revisionId && (
                      <Button onClick={() => setEditing(true)}>
                        Edit configuration
                      </Button>
                    )}
                    {detail?.item.owned && !editing && revisionId && (
                      <Button
                        component={Link}
                        to={`/library/${kind}/${objectId}`}
                        state={returnState}
                      >
                        Open latest version
                      </Button>
                    )}
                    {editable && (
                      <Button
                        variant="default"
                        disabled={busy}
                        onClick={requestDiscardCurrentDraft}
                      >
                        {isNew ? 'Discard draft' : 'Cancel editing'}
                      </Button>
                    )}
                    {editable && (
                      <Button
                        type="submit"
                        leftSection={<IconCheck size={16} />}
                        loading={busy}
                        disabled={invalidInputs > 0 || !document.name.trim() || Boolean(componentSaveBlock)}
                      >
                        Save
                      </Button>
                    )}
                    {editable && (
                      <Button
                        variant="default"
                        disabled={busy || invalidInputs > 0 || Boolean(componentSaveBlock)}
                        onClick={() => void check()}
                      >
                        Check inputs
                      </Button>
                    )}
                    {detail?.item.owned && (
                      <PublishDialog
                        kind={kind}
                        objectId={objectId}
                        disabled={busy || dirty || detail.item.archived}
                      />
                    )}
                    {detail && session && (
                      <Button
                        variant="default"
                        leftSection={<IconCopy size={16} />}
                        disabled={busy || dirty}
                        onClick={() => void duplicate()}
                      >
                        {detail.item.owned ? 'Duplicate' : 'Copy to my library'}
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
                      Version history
                    </Button>
                  )}
                </Group>
              </div>
              {busy && (
                <Text role="status" size="sm" c="dimmed">
                  Checking physical inputs and completing your action…
                </Text>
              )}
              {componentSaveBlock && (
                <Text role="status" size="sm" c="dimmed">
                  {componentSaveBlock}
                </Text>
              )}
              {error && (
                <FormError
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
                      Reload saved item
                    </Button>
                  )}
                </FormError>
              )}
              {message && (
                <Alert color="teal" role="status">
                  {message}
                </Alert>
              )}
              {(editable || validation?.is_valid === false) && (
                <PhysicalStatus
                  validation={validation}
                  stale={serialized !== validated || invalidInputs > 0}
                  setup={kind === 'setups'}
                />
              )}
              {resolved && serialized === validated && (
                <Button variant="subtle" onClick={downloadResolved}>
                  Download resolved CINDER input
                </Button>
              )}
              {editable && !!detail?.updates.length && (
                <Accordion variant="separated">
                  <Accordion.Item value="updates">
                    <Accordion.Control>Component updates</Accordion.Control>
                    <Accordion.Panel>
                      <Stack gap="sm">
                        <Text size="sm">
                          This configuration still uses its saved revisions.
                          Review the differences before applying an update.
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
                              disabledReason={
                                busy
                                  ? 'Wait for the current action.'
                                  : dirty
                                    ? 'Save or discard your working changes first.'
                                    : !editable
                                      ? 'Copy this item into your library before updating it.'
                                      : undefined
                              }
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
                    </Accordion.Panel>
                  </Accordion.Item>
                </Accordion>
              )}
              {kind === 'cvts' && detail && !editable && (
                <Paper withBorder p="lg" id="tunes">
                  <CvtTunes
                    cvtObjectId={detail.item.id}
                    cvtRevisionId={revisionId ?? detail.item.revision_id}
                  />
                </Paper>
              )}
              {!editable ? (
                <ConfigurationView
                  document={document}
                  fields={fields}
                  references={detail?.references}
                />
              ) : (
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
                          onChange={(data) =>
                            setDocument({ ...document, data })
                          }
                          disabled={disabled}
                        />
                      )}
                      {document.kind === 'belts' && (
                        <BeltEditor
                          value={document.data}
                          onChange={(data) =>
                            setDocument({ ...document, data })
                          }
                          disabled={disabled}
                        />
                      )}
                      {document.kind === 'cvts' && (
                        <CvtEditor
                          draftPathPrefix="/data/assembly"
                          value={document.data}
                          onChange={(data) =>
                            setDocument({ ...document, data })
                          }
                          fields={fields}
                          belts={componentItems('belts')}
                          validation={validation}
                          disabled={disabled}
                          onLoadingChange={setComponentLoading}
                          onSaveBlockChange={setComponentSaveBlock}
                          enableInitialTune={isNew}
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
                                        engine: {
                                          ...document.data.engine,
                                          data,
                                        },
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
                                  draftPathPrefix="/data/cvt/data/assembly"
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
                                  validation={validation}
                                  disabled={disabled}
                                  onLoadingChange={setComponentLoading}
                                  onSaveBlockChange={setComponentSaveBlock}
                                  enableInitialTune={!document.data.cvt.revision_id}
                                />
                              </Stack>
                            </Accordion.Panel>
                          </Accordion.Item>
                        </Accordion>
                      )}
                    </Paper>
                  </Stack>
                </fieldset>
              )}

              <Group justify="space-between">
                {detail?.item.owned && (
                  <Button
                    variant="subtle"
                    color="gray"
                    disabledReason={
                      busy
                        ? 'Wait for the current action.'
                        : dirty
                          ? 'Save or discard your working changes first.'
                          : undefined
                    }
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
                    disabledReason={
                      busy
                        ? 'Wait for the current action.'
                        : dirty
                          ? 'Save your changes before building a run.'
                          : detail.item.archived
                            ? 'Unarchive this setup first.'
                            : !detail.validation.is_valid
                              ? 'Correct this setup’s validation errors first.'
                              : undefined
                    }
                  >
                    Build a run with this setup
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
          >
            {editable && (
              <Textarea
                label="Note for the next save"
                value={note}
                maxLength={2000}
                onChange={(event) => setNote(event.currentTarget.value)}
              />
            )}
          </RevisionHistory>
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
                  disabledReason={
                    busy ? 'Wait for the current action.' : undefined
                  }
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
                  setInvalid(new Set());
                  setRetry((value) => value + 1);
                }}
              >
                Discard & reload
              </Button>
            </Group>
          </Stack>
        </Modal>
        <Modal
          opened={discardOpen}
          onClose={() => !busy && setDiscardOpen(false)}
          title={isNew ? 'Discard this draft?' : 'Discard unsaved changes?'}
        >
          <Stack>
            <Text>
              {isNew
                ? 'This new item has not been saved. Discarding it removes this working draft.'
                : 'This restores the latest saved revision and removes your working changes.'}
            </Text>
            <Group justify="end">
              <Button variant="default" onClick={() => setDiscardOpen(false)}>
                Keep editing
              </Button>
              <Button color="red" onClick={discardCurrentDraft}>
                {isNew ? 'Discard draft' : 'Discard changes'}
              </Button>
            </Group>
          </Stack>
        </Modal>
        <Modal
          opened={blocker.state === 'blocked'}
          onClose={() => blocker.state === 'blocked' && blocker.reset()}
          title={isNew ? 'Discard this draft and leave?' : 'Leave unsaved changes?'}
        >
          <Stack>
            <Text>
              {isNew
                ? 'This draft has not been saved.'
                : 'Your working values have not been saved.'}
            </Text>
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
                {isNew ? 'Discard draft & leave' : 'Discard & leave'}
              </Button>
            </Group>
          </Stack>
        </Modal>
      </Stack>
    </Container>
    </EditorHistoryBoundary>
  );
}
