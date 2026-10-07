import { Alert, Stack, Text } from '@mantine/core';
import { runOutcomeColors } from '@styles/theme';
import type { RunInspection } from './api';
import { outcomeDataMessage, outcomeProgress, type RunOutcome } from './runOutcome';
import { useAuth } from '@contexts/AuthContext';

export function RunOutcomeNotice({
  outcome,
  availability,
  showReference = true,
}: {
  outcome: RunOutcome;
  availability?: RunInspection['availability'];
  showReference?: boolean;
}) {
  const { unitPreferences } = useAuth();
  if (outcome.category === 'success') return null;
  const progress = outcomeProgress(outcome, unitPreferences);
  return (
    <Alert color={runOutcomeColors[outcome.category]} title={outcome.title} role="status">
      <Stack gap="xs">
        <Text size="sm">{outcome.message}</Text>
        {outcome.action && <Text size="sm">{outcome.action}</Text>}
        {progress && <Text size="sm" fw={600}>{progress}</Text>}
        <Text size="sm">{outcomeDataMessage(outcome, availability)}</Text>
        {showReference && !['pending', 'success', 'cancelled', 'vehicle_stopped'].includes(outcome.category) && (
          <Text size="xs" c="dimmed" style={{ overflowWrap: 'anywhere' }}>
            Run ID: {outcome.support_run_id}
          </Text>
        )}
      </Stack>
    </Alert>
  );
}
