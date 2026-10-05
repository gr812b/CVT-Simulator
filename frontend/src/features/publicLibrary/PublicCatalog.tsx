import { Tabs } from '@mantine/core';
import { useSearchParams } from 'react-router-dom';
import { kindLabels, isPhysicalKind } from '../physicalLibrary/api';
import {
  LibraryBrowser,
  type LibraryCategory,
} from '../physicalLibrary/LibraryBrowser';
import { RunHistory } from '../results/RunHistory';
import { PublicUsers } from './PublicUsers';

export function PublicCatalog({ authorId }: { authorId?: string }) {
  const [params, setParams] = useSearchParams();
  const requested = params.get('kind') ?? 'setups';
  const selected = requested === 'tunes' ? 'cvts' : requested;
  const kind =
    ['load-cases', 'runs', ...(!authorId ? ['users'] : [])].includes(
      selected,
    ) || isPhysicalKind(selected)
      ? selected
      : 'setups';
  return (
    <>
      <Tabs
        value={kind}
        onChange={(kind) =>
          kind &&
          setParams((current) => {
            const next = new URLSearchParams(current);
            next.set('kind', kind);
            next.delete('page');
            next.delete('user');
            return next;
          })
        }
      >
        <Tabs.List>
          {Object.entries(kindLabels).map(([value, label]) => (
            <Tabs.Tab key={value} value={value}>
              {label}
            </Tabs.Tab>
          ))}
          <Tabs.Tab value="load-cases">Load cases</Tabs.Tab>
          <Tabs.Tab value="runs">Runs</Tabs.Tab>
          {!authorId && <Tabs.Tab value="users">People</Tabs.Tab>}
        </Tabs.List>
      </Tabs>
      {kind === 'users' ? (
        <PublicUsers />
      ) : kind === 'runs' ? (
        <RunHistory publicView authorId={authorId} />
      ) : (
        <LibraryBrowser
          kind={kind as LibraryCategory}
          publicView
          authorId={authorId}
        />
      )}
    </>
  );
}
