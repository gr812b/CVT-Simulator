import { runStatusColors } from '@styles/theme';
import { useAuth } from '@contexts/AuthContext';
import { RunStatusBadge } from '../results/RunStatusBadge';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import { Alert, Badge, Drawer, Group, Stack, Text } from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { IconActivity } from '@tabler/icons-react';
import { Link } from 'react-router-dom';
import {
  getActivity,
  listRuns,
  message,
  readNotice,
  type RunActivity,
  type RunStatus,
} from './api';

const Context = createContext<{
  activity: RunActivity | null;
  error: string | null;
  refresh: () => Promise<void>;
  dismiss: (id: string) => Promise<void>;
} | null>(null);

export function RunActivityProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const enabled = !!session;
  const [activity, setActivity] = useState<RunActivity | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    if (!enabled) return;
    try {
      setActivity(await getActivity());
      setError(null);
    } catch (cause) {
      setError(message(cause));
    }
  }, [enabled]);
  useEffect(() => {
    if (!enabled) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await getActivity();
        if (!disposed) {
          setActivity(next);
          setError(null);
        }
      } catch (cause) {
        if (!disposed) setError(message(cause));
      }
      if (!disposed) timer = setTimeout(poll, 2500);
    };
    void poll();
    const focus = () => void refresh();
    window.addEventListener('focus', focus);
    return () => {
      disposed = true;
      clearTimeout(timer);
      window.removeEventListener('focus', focus);
    };
  }, [refresh, enabled]);
  const dismiss = useCallback(
    async (id: string) => {
      await readNotice(id);
      await refresh();
    },
    [refresh],
  );
  return (
    <Context.Provider value={{ activity, error, refresh, dismiss }}>
      {children}
    </Context.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useRunActivity() {
  const context = useContext(Context);
  if (!context) throw new Error('Run activity provider is missing.');
  return context;
}

export function RunActivityButton() {
  const { activity, error, refresh, dismiss } = useRunActivity();
  const [opened, setOpened] = useState(false);
  const [recent, setRecent] = useState<RunStatus[]>([]);
  const [localError, setLocalError] = useState<string | null>(null);
  const open = async () => {
    setOpened(true);
    setLocalError(null);
    await refresh();
    try {
      setRecent(await listRuns());
    } catch (cause) {
      setLocalError(message(cause));
    }
  };
  return (
    <>
      <Button
        variant="light"
        size="xs"
        leftSection={<IconActivity size={17} />}
        onClick={() => void open()}
        aria-label="Run activity"
      >
        {activity?.active ? activity.active.status : 'Activity'}
        {Boolean(activity?.unread_count) && (
          <Badge size="sm" ml="xs">
            {activity!.unread_count}
          </Badge>
        )}
      </Button>
      <Drawer
        opened={opened}
        onClose={() => setOpened(false)}
        position="right"
        title="Run activity"
      >
        <Stack>
          {(error || localError) && (
            <Alert color="red">{error || localError}</Alert>
          )}
          {activity?.active && (
            <Alert
              color={runStatusColors[activity.active.status]}
              title="Active simulation"
            >
              <Text>
                {activity.active.name} · {activity.active.status}
                {activity.active.queue_position
                  ? ` · queue position ${activity.active.queue_position}`
                  : ''}
              </Text>
              <Button
                component={Link}
                to={`/runs/${activity.active.id}`}
                onClick={() => setOpened(false)}
                variant="light"
                mt="sm"
              >
                View active run
              </Button>
            </Alert>
          )}
          <Text fw={700}>Unread updates</Text>
          {!activity?.unread.length && (
            <Text size="sm" c="dimmed">
              You're all caught up.
            </Text>
          )}
          {activity?.unread.map((notice) => (
            <Stack key={notice.id} gap="xs">
              <Group justify="space-between">
                <Text size="sm" fw={600}>
                  {notice.run.name}
                </Text>
                <RunStatusBadge status={notice.run.status} />
              </Group>
              <Group>
                <Button
                  size="xs"
                  component={Link}
                  to={`/runs/${notice.run.id}`}
                  onClick={() => {
                    setOpened(false);
                    void dismiss(notice.id).catch((cause) =>
                      setLocalError(message(cause)),
                    );
                  }}
                >
                  View run
                </Button>
                <Button
                  size="xs"
                  variant="subtle"
                  onClick={() =>
                    void dismiss(notice.id).catch((cause) =>
                      setLocalError(message(cause)),
                    )
                  }
                >
                  Mark read
                </Button>
              </Group>
            </Stack>
          ))}
          <Text fw={700} mt="md">
            Recent runs
          </Text>
          {recent.map((run) => (
            <Button
              key={run.id}
              component={Link}
              to={`/runs/${run.id}`}
              variant="default"
              justify="space-between"
              onClick={() => setOpened(false)}
              rightSection={<RunStatusBadge size="xs" status={run.status} />}
            >
              <Text truncate size="sm">
                {run.name}
              </Text>
            </Button>
          ))}
        </Stack>
      </Drawer>
    </>
  );
}

export function RunActivityBanner() {
  const { activity, dismiss } = useRunActivity();
  const [error, setError] = useState<string | null>(null);
  const notice = activity?.unread[0];
  if (!notice) return null;
  return (
    <Alert
      mb="md"
      color={runStatusColors[notice.run.status]}
      title={`${notice.run.name} · ${notice.run.status}`}
      role="status"
    >
      <Group justify="space-between">
        <Text size="sm">
          {notice.run.status === 'completed'
            ? 'Your result is ready.'
            : (notice.run.error?.message ?? 'Your simulation has stopped.')}
          {notice.run.has_result &&
            notice.run.status !== 'completed' &&
            ' Saved progress is available for playback.'}
        </Text>
        <Group gap="xs">
          <Button
            component={Link}
            to={`/runs/${notice.run.id}`}
            onClick={() =>
              void dismiss(notice.id).catch((cause) => setError(message(cause)))
            }
            size="xs"
            variant="light"
          >
            View run
          </Button>
          <Button
            size="xs"
            variant="subtle"
            onClick={() =>
              void dismiss(notice.id).catch((cause) => setError(message(cause)))
            }
          >
            Dismiss
          </Button>
        </Group>
      </Group>
      {error && <Text c="red">{error}</Text>}
    </Alert>
  );
}
