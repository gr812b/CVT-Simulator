import { useEffect, useRef, useState } from 'react';
import {
  Accordion,
  Alert,
  Anchor,
  Badge,
  Code,
  Group,
  Loader,
  Modal,
  Paper,
  ScrollArea,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '@contexts/AuthContext';
import { PublicTuneList } from './PublicExperiment';
import { CatalogFrame } from './CatalogFrame';
import { ConfigurationView } from './ConfigurationView';
import {
  comparePublications,
  copyPublication,
  getPublication,
  publicationMetadata,
  sourceLink,
  type PublicationDetail,
} from './api';
import {
  DifferenceList,
  PhysicalStatus,
} from '../physicalLibrary/PhysicalStatus';
import { kindLabels, type PhysicalField } from '../physicalLibrary/api';
import { formatMetric } from '../results/api';
import { message } from '../experiments/api';

export function PublicationPage() {
  const { publicationId } = useParams();
  return <PublicPublication key={publicationId} id={publicationId ?? ''} />;
}

function PublicPublication({ id }: { id: string }) {
  const { session } = useAuth();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<PublicationDetail | null>(null);
  const [fields, setFields] = useState<PhysicalField[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [busy, setBusy] = useState(false);
  const [copying, setCopying] = useState(false);
  const [copyName, setCopyName] = useState('');
  const [comparison, setComparison] = useState<Awaited<
    ReturnType<typeof comparePublications>
  > | null>(null);
  const copyRequest = useRef({ name: '', key: crypto.randomUUID() });
  useEffect(() => {
    const controller = new AbortController();
    setDetail(null);
    setError(null);
    void Promise.all([
      getPublication(id, controller.signal),
      publicationMetadata(),
    ])
      .then(([result, metadata]) => {
        if (!controller.signal.aborted) {
          setDetail(result);
          setFields(metadata.cvt_fields);
          setCopyName(`${result.item.name.slice(0, 230)} (copy)`);
        }
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(message(cause));
      });
    return () => controller.abort();
  }, [id, retry]);
  const task = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(false);
    }
  };
  const copy = () =>
    task(async () => {
      const name = copyName.trim();
      if (copyRequest.current.name !== name)
        copyRequest.current = { name, key: crypto.randomUUID() };
      const result = await copyPublication(id, {
        request_key: copyRequest.current.key,
        name,
      });
      navigate(`/library/${result.item.kind}/${result.item.id}`);
    });
  const latest = detail?.history.find(
    (item) => item.publication_number > detail.item.publication_number,
  );
  return (
    <CatalogFrame>
      <Button
        component={Link}
        to={`/catalog?kind=${detail?.item.kind ?? 'setups'}`}
        variant="subtle"
        w="fit-content"
      >
        Back to public library
      </Button>
      {error && (
        <Alert
          color="red"
          title={detail ? 'Action could not finish' : 'Publication unavailable'}
          role="alert"
        >
          {error}
          {!detail && (
            <>
              <Text size="sm">
                This saved revision could not be found. Existing copies remain
                in their owners’ libraries.
              </Text>
              <Button
                variant="subtle"
                onClick={() => setRetry((value) => value + 1)}
              >
                Try again
              </Button>
            </>
          )}
        </Alert>
      )}
      {!detail ? (
        !error && <Loader aria-label="Loading publication" />
      ) : (
        <>
          <Group justify="space-between" align="start">
            <Stack gap="sm">
              <Group>
                <Badge>{kindLabels[detail.item.kind]}</Badge>
                <Badge variant="outline">{detail.item.visibility}</Badge>
                {detail.item.sample && (
                  <Badge color="blue">Catalog default</Badge>
                )}
              </Group>
              <Title order={1}>{detail.item.name}</Title>
              <Text c="dimmed">
                Published by {detail.item.author} ·{' '}
                {new Date(detail.item.published_at).toLocaleDateString()}
              </Text>
            </Stack>
            {session ? (
              <Button onClick={() => setCopying(true)}>
                Copy to My Library
              </Button>
            ) : (
              <Button
                component={Link}
                to={`/login?next=${encodeURIComponent(`/catalog/${id}`)}`}
              >
                Sign in to copy
              </Button>
            )}
          </Group>
          <Text style={{ whiteSpace: 'pre-wrap' }}>
            {detail.item.description ||
              'A saved configuration with its required component values included.'}
          </Text>
          {detail.item.kind === 'cvts' && (
            <Paper withBorder p="lg" id="tunes">
              <PublicTuneList cvtObjectId={detail.item.source_object_id} />
            </Paper>
          )}
          <Paper withBorder p="lg">
            <Stack>
              <Title order={2} size="h3">
                Configuration summary
              </Title>
              <Text size="sm">
                Copying creates your own item and its required components. Later
                edits to the source do not change your copy.
              </Text>
              <SimpleGrid cols={{ base: 2, sm: 4 }}>
                {detail.item.properties.map((property) => (
                  <div key={property.key}>
                    <Text size="xs" c="dimmed">
                      {property.label}
                    </Text>
                    <Text fw={600}>{formatMetric(property)}</Text>
                  </div>
                ))}
              </SimpleGrid>
              <Text size="sm">
                Source:{' '}
                {detail.item.source_label || 'No source attribution supplied'}
              </Text>
              {sourceLink(detail.item.source_url) && (
                <Anchor
                  href={sourceLink(detail.item.source_url)!}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Source reference
                </Anchor>
              )}
            </Stack>
          </Paper>
          {latest && (
            <Alert color="blue" title="A newer publication is available">
              <Text size="sm">
                This page still shows the fixed values of publication{' '}
                {detail.item.publication_number}.
              </Text>
              <Group mt="sm">
                <Button
                  variant="light"
                  loading={busy}
                  onClick={() =>
                    void task(async () =>
                      setComparison(await comparePublications(id, latest.id)),
                    )
                  }
                >
                  Compare newer publication
                </Button>
                <Button
                  component={Link}
                  to={`/catalog/${latest.id}`}
                  variant="subtle"
                >
                  Open publication {latest.publication_number}
                </Button>
              </Group>
            </Alert>
          )}
          <PhysicalStatus
            validation={detail.validation}
            setup={detail.item.kind === 'setups'}
          />
          <Text size="sm" c="dimmed">
            Input validation checks compatibility with CINDER; it does not
            establish measurement accuracy or experimental validation.
          </Text>
          {detail.dependencies.length > 0 && (
            <Paper withBorder p="lg">
              <Stack>
                <Title order={2} size="h3">
                  Included components
                </Title>
                {detail.dependencies.map((dependency, index) => (
                  <Text key={index} size="sm">
                    {dependency.name} · {dependency.kind}
                  </Text>
                ))}
                <Text size="xs" c="dimmed">
                  These values are embedded in this publication. Source notes
                  and assumptions are included; each revision keeps its original
                  values.
                </Text>
              </Stack>
            </Paper>
          )}
          <ConfigurationView document={detail.document} fields={fields} />
          <Accordion variant="separated">
            <Accordion.Item value="history">
              <Accordion.Control>Version history</Accordion.Control>
              <Accordion.Panel>
                <Paper withBorder p="lg">
                  <Stack>
                    <Title order={2} size="h3">
                      Saved versions
                    </Title>
                    <Group>
                      {detail.history.map((item) => (
                        <Button
                          key={item.id}
                          component={Link}
                          to={`/catalog/${item.id}`}
                          variant={item.id === id ? 'filled' : 'light'}
                        >
                          Publication {item.publication_number} · r
                          {item.revision_number}
                        </Button>
                      ))}
                    </Group>
                  </Stack>
                </Paper>
              </Accordion.Panel>
            </Accordion.Item>
          </Accordion>
          <Modal
            opened={copying}
            onClose={() => !busy && setCopying(false)}
            title="Copy to My Library"
          >
            <Stack>
              <Text size="sm">
                The{' '}
                {detail.item.kind === 'setups'
                  ? 'vehicle, engine, CVT and belt'
                  : detail.item.kind === 'cvts'
                    ? 'CVT and belt'
                    : detail.item.kind === 'belts'
                      ? 'belt'
                      : 'engine'}{' '}
                will become public items in your workspace. Their published
                source will remain recorded.
              </Text>
              <TextInput
                label="Copy name"
                value={copyName}
                maxLength={240}
                onChange={(event) => setCopyName(event.currentTarget.value)}
              />
              {error && <Alert color="red">{error}</Alert>}
              <Button
                loading={busy}
                disabled={!copyName.trim()}
                onClick={() => void copy()}
              >
                Create independent copy
              </Button>
            </Stack>
          </Modal>
          <Modal
            opened={!!comparison}
            onClose={() => setComparison(null)}
            title="Publication differences"
            size="xl"
          >
            {comparison && (
              <Stack>
                <Text>
                  Publication {comparison.before.publication_number} →{' '}
                  {comparison.after.publication_number}. Differences use
                  canonical units. Applying nothing keeps your existing copies
                  unchanged.
                </Text>
                <DifferenceList differences={comparison.differences} />
                <ScrollArea h={180}>
                  <Code block>
                    {JSON.stringify(
                      {
                        before: comparison.before.id,
                        after: comparison.after.id,
                      },
                      null,
                      2,
                    )}
                  </Code>
                </ScrollArea>
              </Stack>
            )}
          </Modal>
        </>
      )}
    </CatalogFrame>
  );
}
