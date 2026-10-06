import { LibraryTabs } from '../physicalLibrary/LibraryTabs';
import { useSearchParams } from 'react-router-dom';
import { isPhysicalKind } from '../physicalLibrary/api';
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
      <LibraryTabs
        runs
        people={!authorId}
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
      />
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
