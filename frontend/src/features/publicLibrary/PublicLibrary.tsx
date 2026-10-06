import { Text, Title } from '@mantine/core';
import { CatalogFrame } from './CatalogFrame';
import { PublicCatalog } from './PublicCatalog';

export function PublicLibrary() {
  return (
    <CatalogFrame>
      <Title order={1}>Public library</Title>
      <Text c="dimmed">
        Free accounts share saved configurations, load cases, tunes and
        simulation results. Find tunes on each CVT’s page.
      </Text>
      <PublicCatalog />
    </CatalogFrame>
  );
}
