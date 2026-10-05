import { Suspense, useState } from 'react';
import {
  Alert,
  AppShell,
  Burger,
  Center,
  Divider,
  Group,
  Loader,
  NavLink,
  Stack,
  Text,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { useDisclosure } from '@mantine/hooks';
import {
  IconChartLine,
  IconGeometry,
  IconHome,
  IconLibrary,
  IconPlayerPlay,
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
    links: [
      { to: '/catalog', label: 'Public library', icon: IconLibrary },
      { to: '/demo', label: 'Playback demo', icon: IconPlayerPlay },
    ],
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
      navbar={{ width: 240, breakpoint: 'sm', collapsed: { mobile: !opened } }}
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
                  {session.user.display_name}
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
      <AppShell.Navbar p="md">
        <AppShell.Section grow style={{ overflowY: 'auto' }}>
          {sections.map((section, index) => (
            <div key={section.label}>
              {index > 0 && <Divider my="lg" />}
              <Text size="xs" c="dimmed" mb="xs" tt="uppercase" fw={700}>
                {section.label}
              </Text>
              {section.links.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  component={Link}
                  to={to}
                  label={label}
                  leftSection={<Icon size={18} />}
                  active={
                    location.pathname === to ||
                    location.pathname.startsWith(`${to}/`)
                  }
                  onClick={close}
                />
              ))}
            </div>
          ))}
        </AppShell.Section>
        {session && (
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
        <Suspense
          fallback={
            <Center mih="60vh">
              <Loader aria-label="Loading page" />
            </Center>
          }
        >
          <Outlet />
        </Suspense>
      </AppShell.Main>
    </AppShell>
  );
  return session ? (
    <RunActivityProvider key={session.user.id}>{shell}</RunActivityProvider>
  ) : (
    shell
  );
}
