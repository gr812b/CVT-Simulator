import { PageLoading } from '@components/loadingOverlay/PageLoading';
import { Suspense, useState } from 'react';
import {
  Alert,
  ActionIcon,
  Tooltip,
  AppShell,
  Burger,
  Center,
  Divider,
  Group,
  Loader,
  NavLink,
  Stack,
  Text,
  useMantineTheme,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { useDisclosure, useLocalStorage, useMediaQuery } from '@mantine/hooks';
import {
  IconLayoutSidebarLeftCollapse,
  IconLayoutSidebarLeftExpand,
  IconChartLine,
  IconGeometry,
  IconHome,
  IconLibrary,
  IconSettings,
  IconTool,
} from '@tabler/icons-react';
import { Link, Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@contexts/AuthContext';
import { SimulationCaseProvider } from '@contexts/SimulationCaseContext';
import { SimulationRunProvider } from '@contexts/SimulationRunContext';
import { LoadingProvider } from '@contexts/LoadingContext';
import {
  RunActivityBanner,
  RunActivityButton,
  RunActivityProvider,
} from '../../features/experiments/RunActivity';
import { Brand } from './Brand';
import { AuthorLink } from '../../features/community/AuthorLink';

const sections = [
  {
    label: 'Design & simulation',
    links: [
      { to: '/dashboard', label: 'Workspace', icon: IconHome },
      { to: '/library', label: 'Physical library', icon: IconLibrary },
      { to: '/input', label: 'Build a run', icon: IconTool },
      { to: '/runs', label: 'Runs & results', icon: IconChartLine },
      { to: '/geometry', label: 'Geometry study', icon: IconGeometry },
    ],
  },
  {
    label: 'Explore',
    links: [{ to: '/catalog', label: 'Public library', icon: IconLibrary }],
  },
  {
    label: 'Account',
    links: [{ to: '/account', label: 'Account settings', icon: IconSettings }],
  },
];

/** Authentication and workspace-only providers are independent of the shared frame. */
export function RequireAccount() {
  const { session } = useAuth();
  const location = useLocation();
  if (!session)
    return (
      <Navigate
        to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`}
        replace
      />
    );
  return (
    <SimulationCaseProvider key={session.user.id}>
      <SimulationRunProvider>
        <LoadingProvider>
          <Outlet />
        </LoadingProvider>
      </SimulationRunProvider>
    </SimulationCaseProvider>
  );
}

export function ApplicationShell() {
  const { session, loading, error, refresh, signOut } = useAuth();
  const location = useLocation();
  const [opened, { toggle, close }] = useDisclosure();
  const [replayNavigation, setReplayNavigation] = useLocalStorage({
    key: 'cinder-replay-navigation',
    defaultValue: true,
  });
  const replay = location.pathname.includes('/playback');
  const theme = useMantineTheme();
  const desktop = useMediaQuery(
    `(min-width: ${theme.breakpoints.sm})`,
    undefined,
    { getInitialValueInEffect: false },
  );
  const compact = replay && !replayNavigation && desktop;
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);
  if (loading)
    return (
      <Center mih="100dvh">
        <Loader aria-label="Loading your workspace" />
      </Center>
    );
  if (error)
    return (
      <Center mih="100dvh">
        <Stack>
          <Alert color="red">{error}</Alert>
          <Button onClick={() => void refresh()}>Try again</Button>
        </Stack>
      </Center>
    );
  const logout = async () => {
    setSigningOut(true);
    setSignOutError(null);
    try {
      await signOut();
    } catch {
      setSignOutError('Unable to sign out. Please try again.');
    } finally {
      setSigningOut(false);
    }
  };
  const shell = (
    <AppShell
      header={{ height: 64 }}
      navbar={{
        width: replay && !replayNavigation ? 56 : 240,
        breakpoint: 'sm',
        collapsed: { mobile: !opened },
      }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="lg" justify="space-between">
          <Group>
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="sm"
              size="sm"
              aria-label="Toggle navigation"
            />
            <Brand />
          </Group>
          <Group gap="sm">
            {session ? (
              <>
                <RunActivityButton />
                <Text size="sm" truncate maw={180} visibleFrom="sm">
                  <AuthorLink
                    name={session.user.display_name}
                    id={session.user.id}
                  />
                </Text>
              </>
            ) : (
              <Button component={Link} to="/login" variant="default">
                Sign in
              </Button>
            )}
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p={compact ? 8 : 'md'} id="workspace-navigation">
        {replay && (
          <AppShell.Section visibleFrom="sm" mb="md">
            <Group justify="space-between">
              {!compact && (
                <Text size="sm" fw={600}>
                  Navigation
                </Text>
              )}
              <Tooltip
                label={compact ? 'Expand navigation' : 'Collapse navigation'}
                withArrow
              >
                <ActionIcon
                  variant="default"
                  aria-label={
                    compact ? 'Expand navigation' : 'Collapse navigation'
                  }
                  aria-expanded={!compact}
                  aria-controls="workspace-navigation"
                  onClick={() => setReplayNavigation(!replayNavigation)}
                >
                  {compact ? (
                    <IconLayoutSidebarLeftExpand size={18} />
                  ) : (
                    <IconLayoutSidebarLeftCollapse size={18} />
                  )}
                </ActionIcon>
              </Tooltip>
            </Group>
          </AppShell.Section>
        )}
        <AppShell.Section grow style={{ overflowY: 'auto' }}>
          {sections.map((section, index) => (
            <div key={section.label}>
              {index > 0 && <Divider my="lg" />}
              {!compact && (
                <Text size="xs" c="dimmed" mb="xs" tt="uppercase" fw={700}>
                  {section.label}
                </Text>
              )}
              {section.links.map(({ to, label, icon: Icon }) => (
                <Tooltip
                  key={to}
                  label={label}
                  disabled={!compact}
                  position="right"
                >
                  <NavLink
                    component={Link}
                    to={to}
                    label={compact ? undefined : label}
                    aria-label={label}
                    styles={
                      compact
                        ? {
                            root: { padding: 10 },
                            section: { marginInlineEnd: 0 },
                          }
                        : undefined
                    }
                    leftSection={<Icon size={18} />}
                    active={
                      location.pathname === to ||
                      location.pathname.startsWith(`${to}/`)
                    }
                    onClick={close}
                  />
                </Tooltip>
              ))}
            </div>
          ))}
        </AppShell.Section>
        {session && !compact && (
          <AppShell.Section pt="md">
            <Stack gap="sm">
              <Text size="xs" c="dimmed" truncate>
                {session.account.name}
              </Text>
              {signOutError && (
                <Alert color="red" role="alert">
                  {signOutError}
                </Alert>
              )}
              <Button
                variant="default"
                loading={signingOut}
                onClick={() => void logout()}
              >
                Sign out
              </Button>
            </Stack>
          </AppShell.Section>
        )}
      </AppShell.Navbar>
      <AppShell.Main>
        {session && <RunActivityBanner />}
        <Suspense fallback={<PageLoading message="Loading page…" />}>
          <Outlet />
        </Suspense>
      </AppShell.Main>
    </AppShell>
  );
  return (
    <RunActivityProvider key={session?.user.id ?? 'public'}>
      {shell}
    </RunActivityProvider>
  );
}
