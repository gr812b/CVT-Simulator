import { useState } from 'react';
import {
  Alert,
  AppShell,
  Badge,
  Burger,
  Button,
  Center,
  Group,
  Loader,
  NavLink,
  Stack,
  Text,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconChartLine,
  IconFlask,
  IconGeometry,
  IconHome,
  IconSettings,
  IconTool,
} from '@tabler/icons-react';
import { Link, Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@contexts/AuthContext';
import { SimulationCaseProvider } from '@contexts/SimulationCaseContext';
import { SimulationRunProvider } from '@contexts/SimulationRunContext';
import { LoadingProvider } from '@contexts/LoadingContext';

const navigation = [
  { to: '/dashboard', label: 'Workspace', icon: IconHome },
  { to: '/input', label: 'Tune & run', icon: IconTool },
  { to: '/playback', label: 'Run playback', icon: IconChartLine },
  { to: '/geometry', label: 'Geometry study', icon: IconGeometry },
  { to: '/primary-design', label: 'Primary design', icon: IconTool },
  { to: '/validation', label: 'Dyno validation', icon: IconFlask },
  { to: '/account', label: 'Account settings', icon: IconSettings },
];

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
  if (!session)
    return (
      <Navigate
        to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`}
        replace
      />
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
  return (
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
            <Text component={Link} to="/dashboard" fw={900} size="xl" c="red.4" td="none">
              CINDER
            </Text>
            <Badge variant="light" visibleFrom="sm">
              Workspace
            </Badge>
          </Group>
          <Text size="sm" truncate maw={180}>
            {session.user.display_name}
          </Text>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="md">
        <AppShell.Section grow>
          <Text size="xs" c="dimmed" mb="md" tt="uppercase" fw={700}>
            Design & simulation
          </Text>
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              component={Link}
              to={to}
              label={label}
              leftSection={<Icon size={18} />}
              active={location.pathname === to || location.pathname.startsWith(`${to}/`)}
              onClick={close}
            />
          ))}
        </AppShell.Section>
        <AppShell.Section>
          <Stack gap="sm">
            <Text size="xs" c="dimmed" truncate>
              {session.account.name}
            </Text>
            {signOutError && (
              <Alert color="red" role="alert">
                {signOutError}
              </Alert>
            )}
            <Button variant="default" loading={signingOut} onClick={() => void logout()}>
              Sign out
            </Button>
          </Stack>
        </AppShell.Section>
      </AppShell.Navbar>
      <AppShell.Main>
        <SimulationCaseProvider key={session.user.id}>
          <SimulationRunProvider>
            <LoadingProvider>
              <Outlet />
            </LoadingProvider>
          </SimulationRunProvider>
        </SimulationCaseProvider>
      </AppShell.Main>
    </AppShell>
  );
}
