import { physicalDetailPath } from '../physicalLibrary/links';
import { useEffect, useState } from 'react';
import { Alert, Group, Loader, Stack } from '@mantine/core';
import { Link } from 'react-router-dom';
import { ActionButton as Button } from '@components/button/ActionButton';
import { useAuth } from '@contexts/AuthContext';
import { ConfigurationLink } from '../physicalLibrary/ConfigurationLink';
import {
  getTuneSurface,
  archiveExperiment,
  message,
  type ExperimentDetail,
  type TuneSurface,
} from './api';
import { TuneDialog } from './TuneDialog';
import { TuneEditor } from './TuneEditor';

export function TuneDetails({
  detail,
  onSaved,
  historical,
}: {
  detail: ExperimentDetail;
  onSaved: (value: ExperimentDetail) => void;
  historical: boolean;
}) {
  const { session } = useAuth();
  const [surface, setSurface] = useState<TuneSurface | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<'edit' | 'copy' | null>(null);
  const [working, setWorking] = useState(false);
  const revision =
    detail.document.kind === 'tunes' ? detail.document.cvt_revision_id : '';
  useEffect(() => {
    let disposed = false;
    setSurface(null);
    setError(null);
    void getTuneSurface(revision)
      .then((next) => {
        if (!disposed) setSurface(next);
      })
      .catch((cause) => {
        if (!disposed) setError(message(cause));
      });
    return () => {
      disposed = true;
    };
  }, [revision]);
  if (detail.document.kind !== 'tunes') return null;
  const href = `/input?tune=${detail.item.id}&tune_revision=${detail.item.revision_id}`;
  return (
    <Stack>
      <Group>
        <Button
          component={Link}
          to={session ? href : `/login?next=${encodeURIComponent(href)}`}
        >
          Use this tune
        </Button>
        {session && surface && (
          <>
            {detail.item.owned && !detail.item.archived && !historical && (
              <Button variant="light" onClick={() => setMode('edit')}>
                Edit tune
              </Button>
            )}
            <Button variant="default" onClick={() => setMode('copy')}>
              Duplicate tune
            </Button>
            {detail.item.owned && !historical && (
              <Button
                variant="subtle"
                loading={working}
                disabledReason={
                  !detail.item.archived &&
                  surface.default_tune.item.id === detail.item.id
                    ? 'Choose another default tune on the CVT page before archiving this one.'
                    : undefined
                }
                onClick={() => {
                  setWorking(true);
                  setError(null);
                  void archiveExperiment(detail)
                    .then(() =>
                      onSaved({
                        ...detail,
                        item: {
                          ...detail.item,
                          archived: !detail.item.archived,
                        },
                      }),
                    )
                    .catch((cause) => setError(message(cause)))
                    .finally(() => setWorking(false));
                }}
              >
                {detail.item.archived ? 'Unarchive' : 'Archive'}
              </Button>
            )}
          </>
        )}
      </Group>
      {error && <Alert color="red">{error}</Alert>}
      {surface ? (
        <>
          <ConfigurationLink
            to={physicalDetailPath('cvts', surface.cvt_object_id, surface.cvt_revision_id)}
            from={detail.document.name}
          >
            {surface.cvt_name}
          </ConfigurationLink>
          <TuneEditor
            value={detail.document}
            surface={surface}
            onChange={() => undefined}
            readOnly
          />
        </>
      ) : (
        !error && <Loader />
      )}
      {mode && surface && (
        <TuneDialog
          mode={mode}
          initial={detail.document}
          detail={detail}
          surface={surface}
          onClose={() => setMode(null)}
          onSaved={(next) => {
            setMode(null);
            onSaved(next);
          }}
        />
      )}
    </Stack>
  );
}
