import { Alert, Badge, Group, List, Stack, Text } from '@mantine/core';
import type { PhysicalDifference, PhysicalValidation } from './api';

export function PhysicalStatus({
  validation,
  stale = false,
  setup = false,
}: {
  validation: PhysicalValidation | null;
  stale?: boolean;
  setup?: boolean;
}) {
  if (stale || !validation)
    return (
      <Text size="sm" c="dimmed">
        Working values have changed. Check inputs or save to refresh validation.
      </Text>
    );
  return (
    <Stack gap="xs">
      <Group>
        <Badge color={validation.is_valid ? 'teal' : 'red'} variant="light">
          {validation.is_valid
            ? setup
              ? 'Ready to simulate'
              : 'Inputs valid'
            : 'Needs attention'}
        </Badge>
      </Group>
      {validation.findings.length > 0 && (
        <Alert
          color={validation.is_valid ? 'yellow' : 'red'}
          title="Input checks"
        >
          <List size="sm" spacing="xs">
            {validation.findings.map((finding, index) => (
              <List.Item key={`${finding.code}-${index}`}>
                {finding.message}
                {finding.document_path && (
                  <Text size="xs" c="dimmed">
                    {finding.document_path}
                  </Text>
                )}
              </List.Item>
            ))}
          </List>
        </Alert>
      )}
      {setup && validation.is_valid && (
        <Text size="xs" c="dimmed">
          Checked with the baseline launch and execution settings. Your
          experiment is checked again before it runs.
        </Text>
      )}
    </Stack>
  );
}

export function DifferenceList({
  differences,
}: {
  differences: PhysicalDifference[];
}) {
  if (!differences.length)
    return (
      <Text size="sm">
        These revisions have the same physical values and metadata.
      </Text>
    );
  return (
    <Stack gap="sm">
      {differences.map((change) => (
        <div key={change.path}>
          <Text fw={600} size="sm" style={{ overflowWrap: 'anywhere' }}>
            {change.path
              .replace(/^\/data\//, '')
              .replace(/\//g, ' › ')
              .replace(/_/g, ' ')}
          </Text>
          <Text size="sm" c="dimmed" style={{ overflowWrap: 'anywhere' }}>
            {change.before} → {change.after}
          </Text>
        </div>
      ))}
    </Stack>
  );
}
