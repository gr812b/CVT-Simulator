import { useContext, useEffect, useId, useRef, useState } from 'react';
import { Alert, Select, SimpleGrid, Stack, Text } from '@mantine/core';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import { QuantityValidationContext } from '@components/quantityInput/validation';
import { resolveBeltSection, type BeltData, type BeltSection } from './api';

const sectionFields = [
  { key: 'outer_width_m', label: 'Top width', unit: 'mm' },
  { key: 'inner_width_m', label: 'Bottom width', unit: 'mm' },
  { key: 'height_m', label: 'Belt height', unit: 'mm' },
  { key: 'half_angle_rad', label: 'Belt half-angle', unit: 'deg' },
] as const;
type SectionKey = (typeof sectionFields)[number]['key'];
const sectionOf = (value: BeltData): BeltSection => ({
  outer_width_m: value.outer_width_m,
  inner_width_m: value.inner_width_m,
  height_m: value.height_m,
  half_angle_rad: value.half_angle_rad,
});

export function BeltEditor({
  value,
  onChange,
  disabled = false,
}: {
  value: BeltData;
  onChange: (value: BeltData) => void;
  disabled?: boolean;
}) {
  const [derived, setDerived] = useState<SectionKey>('half_angle_rad');
  const [draft, setDraft] = useState(() => sectionOf(value));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const validation = useContext(QuantityValidationContext);
  const id = useId();
  const latest = useRef({ value, onChange });
  latest.current = { value, onChange };
  const committed = JSON.stringify(sectionOf(value));
  const emitted = useRef(committed);
  useEffect(() => {
    if (committed !== emitted.current) {
      emitted.current = committed;
      setDraft(JSON.parse(committed) as BeltSection);
    }
  }, [committed]);
  useEffect(() => {
    if (disabled) return;
    const controller = new AbortController();
    setPending(true);
    setError(null);
    const timer = window.setTimeout(() => {
      void resolveBeltSection(
        { ...draft, [derived]: undefined },
        controller.signal,
      )
        .then((section) => {
          if (controller.signal.aborted) return;
          emitted.current = JSON.stringify(
            sectionOf({ ...latest.current.value, ...section }),
          );
          latest.current.onChange({ ...latest.current.value, ...section });
        })
        .catch((cause: unknown) => {
          if (!controller.signal.aborted)
            setError(
              cause instanceof Error
                ? cause.message
                : 'Check these belt measurements.',
            );
        })
        .finally(() => {
          if (!controller.signal.aborted) setPending(false);
        });
    }, 180);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [draft, derived, disabled]);
  useEffect(() => {
    validation?.((previous) => {
      const next = new Set(previous);
      if (!disabled && (pending || error)) next.add(id);
      else next.delete(id);
      return next;
    });
    return () => {
      validation?.((previous) => {
        const next = new Set(previous);
        next.delete(id);
        return next;
      });
    };
  }, [validation, id, pending, error, disabled]);
  const patch = (changes: Partial<BeltData>) =>
    onChange({ ...value, ...changes });
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        Enter three section measurements; CINDER calculates the fourth. The
        half-angle is half the included angle between the belt’s sides.
      </Text>
      <Select
        label="Calculate from the other three"
        value={derived}
        data={sectionFields.map(({ key, label }) => ({ value: key, label }))}
        disabled={disabled}
        allowDeselect={false}
        onChange={(next) => {
          if (next) {
            setDraft(sectionOf(value));
            setDerived(next as SectionKey);
          }
        }}
      />
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        {sectionFields.map(({ key, label, unit }) => (
          <QuantityInput
            key={key}
            label={label}
            unit={unit}
            min={Number.MIN_VALUE}
            max={
              key === 'half_angle_rad'
                ? Math.PI / 2 - Number.EPSILON
                : undefined
            }
            value={key === derived ? value[key] : draft[key]}
            disabled={disabled || key === derived}
            description={
              key === derived
                ? pending
                  ? 'Calculating…'
                  : 'Calculated from your other three measurements'
                : undefined
            }
            onChange={(next) => {
              setPending(true);
              setDraft((previous) => ({ ...previous, [key]: next }));
            }}
          />
        ))}
      </SimpleGrid>
      {error && (
        <Alert color="red" role="alert">
          {error}
        </Alert>
      )}
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <QuantityInput
          label="Outer circumference"
          description="Length around the belt’s outer surface, not pitch or nominal length."
          value={value.outer_length_m}
          unit="mm"
          min={Number.MIN_VALUE}
          disabled={disabled}
          onChange={(next) => patch({ outer_length_m: next })}
        />
        <QuantityInput
          label="Cord depth from outer surface"
          value={value.cord_depth_from_outer_m}
          unit="mm"
          min={0}
          max={value.height_m}
          disabled={disabled}
          onChange={(next) => patch({ cord_depth_from_outer_m: next })}
        />
        <QuantityInput
          label="Belt density"
          value={value.density_kg_per_m3}
          unit="kg/m³"
          min={Number.MIN_VALUE}
          disabled={disabled}
          onChange={(next) => patch({ density_kg_per_m3: next })}
        />
      </SimpleGrid>
    </Stack>
  );
}
