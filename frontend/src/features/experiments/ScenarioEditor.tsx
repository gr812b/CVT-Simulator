import { Accordion, Checkbox, Select, SimpleGrid, Stack, Text } from '@mantine/core';
import { QuantityInput } from '@components/quantityInput/QuantityInput';
import { RoadEditor } from './RoadEditor';
import type { ExperimentMetadata, Scenario } from './api';

export function ScenarioEditor({
  value,
  showRoad = true,
  metadata,
  onChange,
  onRoadValidityChange,
}: {
  value: Scenario;
  showRoad?: boolean;
  metadata: ExperimentMetadata;
  onChange: (scenario: Scenario) => void;
  onRoadValidityChange: (valid: boolean) => void;
}) {
  const initial = value.initial!;
  const execution = value.execution!;
  const stops = value.stops;
  const setStops = (patch: Partial<NonNullable<Scenario['stops']>>) =>
    onChange({ ...value, stops: { ...stops, ...patch } });
  return (
    <Stack>
      <Select
        label="Stop at" allowDeselect={false}
        value={stops?.mode ?? 'course'}
        data={[
          { value: 'course', label: 'Course finish' },
          { value: 'timed', label: 'Specified simulation time' },
        ]}
        onChange={mode => setStops({ mode: mode === 'timed' ? 'timed' : 'course' })}
      />
      <QuantityInput
        label={value.stops?.mode === 'timed' ? 'Simulation duration' : 'Maximum simulated time'}
        unit="s"
        scale={1}
        min={0.001}
        max={metadata.limits.max_duration_s}
        value={value.duration_s ?? metadata.scenario_template.duration_s ?? 180}
        onChange={(duration_s) => onChange({ ...value, duration_s })}
      />
      {showRoad && (
        <RoadEditor
          value={value.road}
          metadata={metadata}
          onChange={(road) => onChange({ ...value, road })}
          onValidityChange={onRoadValidityChange}
        />
      )}
      <Accordion variant="separated" multiple>
        {stops?.mode !== 'timed' && (
          <Accordion.Item value="stops">
            <Accordion.Control>Early stopping rules</Accordion.Control>
            <Accordion.Panel>
              <Stack>
                <Text size="sm" c="dimmed">
                  Partial results remain available. Forward progress means gaining
                  at least 5 cm beyond the furthest point reached.
                </Text>
                <Checkbox
                  label="Stop after rolling back" checked={stops?.rollback_m !== null}
                  onChange={e => setStops({ rollback_m: e.currentTarget.checked ? 5 : null })}
                />
                {stops?.rollback_m !== null && (
                  <QuantityInput
                    scope="course"
                    label="Rollback from furthest point" unit="m" min={0.05} scale={1}
                    value={stops?.rollback_m ?? 5}
                    onChange={rollback_m => setStops({ rollback_m })}
                  />
                )}
                <Checkbox
                  label="Stop without forward progress" checked={stops?.no_progress_s !== null}
                  onChange={e => setStops({ no_progress_s: e.currentTarget.checked ? 5 : null })}
                />
                {stops?.no_progress_s !== null && (
                  <QuantityInput
                    label="Time without forward progress" unit="s" min={0.1} scale={1}
                    value={stops?.no_progress_s ?? 5}
                    onChange={no_progress_s => setStops({ no_progress_s })}
                  />
                )}
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        )}
        <Accordion.Item value="initial">
          <Accordion.Control>Initial conditions</Accordion.Control>
          <Accordion.Panel>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <QuantityInput
                label="Initial engine speed"
                unit="RPM"
                scale={60 / (2 * Math.PI)}
                value={initial.primary_angular_speed_rad_per_s ?? 0}
                onChange={(primary_angular_speed_rad_per_s) =>
                  onChange({
                    ...value,
                    initial: { ...initial, primary_angular_speed_rad_per_s },
                  })
                }
              />
              <QuantityInput
                label="Initial secondary speed"
                unit="RPM"
                scale={60 / (2 * Math.PI)}
                value={initial.secondary_angular_speed_rad_per_s ?? 0}
                onChange={(secondary_angular_speed_rad_per_s) =>
                  onChange({
                    ...value,
                    initial: { ...initial, secondary_angular_speed_rad_per_s },
                  })
                }
              />
              <QuantityInput
                label="Initial belt speed"
                unit="m/s"
                scale={1}
                value={initial.belt_speed_m_per_s ?? 0}
                onChange={(belt_speed_m_per_s) =>
                  onChange({
                    ...value,
                    initial: { ...initial, belt_speed_m_per_s },
                  })
                }
              />
              <QuantityInput
                scope="hardware"
                label="Initial shift position"
                unit="mm"
                scale={1000}
                value={initial.shift_position_m ?? 0}
                onChange={(shift_position_m) =>
                  onChange({
                    ...value,
                    initial: { ...initial, shift_position_m },
                  })
                }
              />
              <QuantityInput
                label="Initial shift speed"
                unit="m/s"
                scale={1}
                value={initial.shift_speed_m_per_s ?? 0}
                onChange={(shift_speed_m_per_s) =>
                  onChange({
                    ...value,
                    initial: { ...initial, shift_speed_m_per_s },
                  })
                }
              />
              <QuantityInput
                scope="course"
                label="Initial road distance"
                unit="m"
                scale={1}
                value={initial.vehicle_distance_m ?? 0}
                onChange={(vehicle_distance_m) =>
                  onChange({
                    ...value,
                    initial: { ...initial, vehicle_distance_m },
                  })
                }
              />
            </SimpleGrid>
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="execution">
          <Accordion.Control>Advanced numerical settings</Accordion.Control>
          <Accordion.Panel>
            <Stack>
              <Text size="sm" c="dimmed">
                These settings control numerical execution, not the physical
                design. At most{' '}
                {metadata.limits.max_report_samples.toLocaleString()} reported
                samples; each job has a {metadata.limits.wall_timeout_s} s
                wall-clock limit.
              </Text>
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <QuantityInput
                  label="Relative tolerance"
                  value={execution.relative_tolerance ?? null}
                  onChange={(relative_tolerance) =>
                    onChange({
                      ...value,
                      execution: { ...execution, relative_tolerance },
                    })
                  }
                />
                <QuantityInput
                  label="Absolute tolerance"
                  value={execution.absolute_tolerance ?? null}
                  onChange={(absolute_tolerance) =>
                    onChange({
                      ...value,
                      execution: { ...execution, absolute_tolerance },
                    })
                  }
                />
                <QuantityInput
                  label="Maximum solver step"
                  unit="s"
                  scale={1}
                  value={execution.maximum_step_s ?? null}
                  onChange={(maximum_step_s) =>
                    onChange({
                      ...value,
                      execution: { ...execution, maximum_step_s },
                    })
                  }
                />
                <QuantityInput
                  label="Reporting step"
                  unit="s"
                  scale={1}
                  value={execution.reporting_step_s ?? null}
                  onChange={(reporting_step_s) =>
                    onChange({
                      ...value,
                      execution: { ...execution, reporting_step_s },
                    })
                  }
                />
                <QuantityInput
                  label="Maximum transitions"
                  integer
                  value={execution.maximum_transitions ?? null}
                  onChange={(maximum_transitions) =>
                    onChange({
                      ...value,
                      execution: { ...execution, maximum_transitions },
                    })
                  }
                />
              </SimpleGrid>
            </Stack>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  );
}
