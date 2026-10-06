import { ProfileChart } from '@components/form/ProfileChart';
import type { ReactNode } from 'react';
import { Alert, Group, Select, SimpleGrid, Stack, Text } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import type { ExperimentSelection } from './api';

export type PrimaryBoundary = ExperimentSelection['primary_boundary'];

export function PrimaryBoundaryEditor({
  value,
  onChange,
  children,
}: {
  value: PrimaryBoundary;
  onChange: (value: PrimaryBoundary) => void;
  children: ReactNode;
}) {
  return (
    <Stack>
      <Select
        label="Primary shaft boundary"
        value={value?.kind ?? 'engine'}
        allowDeselect={false}
        data={[
          { value: 'engine', label: 'Engine · full-open-throttle (FOT)' },
          { value: 'fixed_shaft', label: 'Applied torque and inertia' },
          {
            value: 'speed_replay_shaft',
            label: 'Speed-profile tracking (advanced)',
          },
        ]}
        onChange={(kind) =>
          onChange(
            kind === 'fixed_shaft'
              ? { kind, external_torque_Nm: 20, equivalent_inertia_kg_m2: 0.3 }
              : kind === 'speed_replay_shaft'
                ? {
                  kind,
                  tracking_gain_Nm_s_per_rad: 400,
                  speed_reference: {
                    points: [
                      { time_s: 0, value: (1800 * Math.PI) / 30 },
                      { time_s: 10, value: (3600 * Math.PI) / 30 },
                    ],
                  },
                }
                : null,
          )
        }
      />
      {!value ? (
        children
      ) : value.kind === 'fixed_shaft' ? (
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <QuantityInput
            label="Applied primary torque"
            unit="N·m"
            scale={1}
            value={value.external_torque_Nm}
            onChange={(external_torque_Nm) =>
              onChange({ ...value, external_torque_Nm })
            }
            description="Positive torque drives the primary; negative torque resists positive rotation."
          />
          <QuantityInput
            label="External primary inertia"
            unit="kg·m²"
            scale={1}
            min={0}
            value={value.equivalent_inertia_kg_m2}
            onChange={(equivalent_inertia_kg_m2) =>
              onChange({ ...value, equivalent_inertia_kg_m2 })
            }
          />
        </SimpleGrid>
      ) : (
        <Stack>
          <Alert title="Track a target RPM profile">
            CINDER applies a corrective torque to follow this profile. Actual
            speed remains a simulated result; this is not a physical motor
            model. Use the default tight integration settings.
          </Alert>
          <ProfileChart xLabel="Time (s)" yLabel="Speed (RPM)"
            points={value.speed_reference.points.map(point => [point.time_s, point.value * 30 / Math.PI])} />
          {value.speed_reference.points.map((point, index) => (
            <Group key={index} align="end" wrap="wrap">
              <QuantityInput
                label={`Point ${index + 1} time`}
                unit="s"
                scale={1}
                min={0}
                value={point.time_s}
                onChange={(time_s) =>
                  onChange({
                    ...value,
                    speed_reference: {
                      points: value.speed_reference.points.map((p, i) =>
                        i === index ? { ...p, time_s } : p,
                      ),
                    },
                  })
                }
              />
              <QuantityInput
                label={`Point ${index + 1} speed`}
                unit="RPM"
                scale={30 / Math.PI}
                min={0}
                value={point.value}
                onChange={(speed) =>
                  onChange({
                    ...value,
                    speed_reference: {
                      points: value.speed_reference.points.map((p, i) =>
                        i === index ? { ...p, value: speed } : p,
                      ),
                    },
                  })
                }
              />
              <Button
                variant="subtle"
                disabledReason={
                  value.speed_reference.points.length <= 2
                    ? 'A speed profile needs at least two points.'
                    : undefined
                }
                onClick={() =>
                  onChange({
                    ...value,
                    speed_reference: {
                      points: value.speed_reference.points.filter(
                        (_, i) => i !== index,
                      ),
                    },
                  })
                }
              >
                Remove point {index + 1}
              </Button>
            </Group>
          ))}
          <Button
            variant="light"
            disabledReason={
              value.speed_reference.points.length >= 1000
                ? 'The profile has reached its 1,000-point limit.'
                : undefined
            }
            onClick={() => {
              const last = value.speed_reference.points.at(-1)!;
              onChange({
                ...value,
                speed_reference: {
                  points: [
                    ...value.speed_reference.points,
                    { ...last, time_s: last.time_s + 1 },
                  ],
                },
              });
            }}
          >
            Add speed point
          </Button>
          <QuantityInput
            label="Tracking gain"
            value={value.tracking_gain_Nm_s_per_rad ?? 400}
            unit="N·m·s/rad"
            min={0.001}
            scale={1}
            onChange={(tracking_gain_Nm_s_per_rad) =>
              onChange({ ...value, tracking_gain_Nm_s_per_rad })
            }
          />
          <Text size="xs" c="dimmed">
            Start at time zero and use strictly increasing times. The last
            target speed continues beyond the final point.
          </Text>
        </Stack>
      )}
    </Stack>
  );
}
