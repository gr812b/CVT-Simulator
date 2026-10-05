import { Tabs, Text, Title } from '@mantine/core';
import { useSearchParams } from 'react-router-dom';
import { kindLabels, isPhysicalKind } from '../physicalLibrary/api';
import {
  LibraryBrowser,
  type LibraryCategory,
} from '../physicalLibrary/LibraryBrowser';
import { CatalogFrame } from './CatalogFrame';
import { RunHistory } from '../results/RunHistory';
import { PublicUsers } from './PublicUsers';

export function PublicLibrary() {
  const [params, setParams] = useSearchParams();
  const requested = params.get('kind') ?? 'setups';
  const selected = requested === 'tunes' ? 'cvts' : requested;
  const kind =
    ['load-cases', 'runs', 'users'].includes(selected) ||
    isPhysicalKind(selected)
      ? selected
      : 'setups';
  return (
    <CatalogFrame>
      <Title order={1}>Public library</Title>
      <Text c="dimmed">
        Free accounts share saved configurations, load cases, tunes and
        simulation results. Find tunes on each CVT’s page.
      </Text>
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
          <Tabs.Tab value="users">People</Tabs.Tab>
        </Tabs.List>
      </Tabs>
      {kind === 'users' ? (
        <PublicUsers />
      ) : kind === 'runs' ? (
        <RunHistory publicView />
      ) : (
        <LibraryBrowser kind={kind as LibraryCategory} publicView />
      )}
    </CatalogFrame>
  );
}
