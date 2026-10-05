import { runStatusColors } from '@styles/theme';
import { Badge, type BadgeProps } from '@mantine/core';
import type { RunStatus } from '../experiments/api';

export function RunStatusBadge({
  status,
  ...props
}: BadgeProps & { status: RunStatus['status'] }) {
  return (
    <Badge variant="light" {...props} color={runStatusColors[status]}>
      {status.replace(/_/g, ' ')}
    </Badge>
  );
}
