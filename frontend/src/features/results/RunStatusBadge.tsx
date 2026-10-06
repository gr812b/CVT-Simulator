import { runOutcomeColors, runStatusColors } from '@styles/theme';
import { Badge, type BadgeProps } from '@mantine/core';
import type { RunStatus } from '../experiments/api';
import { describeRunOutcome, outcomeLabel, type RunOutcome } from './runOutcome';

export function RunStatusBadge({
  run,
  outcome: suppliedOutcome,
  ...props
}: BadgeProps & { run: RunStatus; outcome?: RunOutcome }) {
  const outcome = suppliedOutcome ?? describeRunOutcome(run);
  return (
    <Badge variant="light" {...props} color={outcome.category === 'pending'
      ? runStatusColors[run.status] : runOutcomeColors[outcome.category]}>
      {outcomeLabel(outcome, run.status)}
    </Badge>
  );
}
