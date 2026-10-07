import { Accordion, Select, SimpleGrid, Stack, Text } from '@mantine/core';
import {
  QUANTITY_LABELS, extraPreferenceDimensions, preferredDisplayUnit, unitsForDimension,
  type DisplayUnit, type PreferenceScope, type QuantityDimension, type UnitPreferences,
} from '@utils/units';

export function UnitPreferenceFields({ scope, value, onChange }: {
  scope: PreferenceScope;
  value: UnitPreferences;
  onChange: (next: UnitPreferences) => void;
}) {
  const dimensions = extraPreferenceDimensions(scope);
  const prominent = dimensions.filter(d => d === 'area' || d === 'inertia');
  const other = dimensions.filter(d => d !== 'area' && d !== 'inertia');
  const input = (dimension: QuantityDimension) => <Select
    key={dimension}
    label={QUANTITY_LABELS[dimension]}
    aria-label={`${scope} ${QUANTITY_LABELS[dimension].toLowerCase()} units`}
    value={preferredDisplayUnit(dimension, scope, value)}
    allowDeselect={false}
    data={unitsForDimension(dimension)}
    onChange={unit => {
      if (!unit) return;
      onChange({ ...value, quantity_units: { ...value.quantity_units,
        [scope]: { ...value.quantity_units[scope], [dimension]: unit as DisplayUnit },
      } });
    }}
  />;
  return <Stack gap="sm">
    <SimpleGrid cols={{ base: 1, sm: 2 }}>{prominent.map(input)}</SimpleGrid>
    <Accordion variant="contained">
      <Accordion.Item value="other-units">
        <Accordion.Control>Other {scope} units</Accordion.Control>
        <Accordion.Panel>
          <Stack gap="sm">
            <Text size="xs" c="dimmed">These choices are independent. lbm means pound-mass; lbf means pound-force. Times remain seconds.</Text>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>{other.map(input)}</SimpleGrid>
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  </Stack>;
}
