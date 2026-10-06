import { useState } from 'react';
import { Alert, Group, Stack } from '@mantine/core';
import { Link } from 'react-router-dom';
import { ActionButton as Button } from '@components/button/ActionButton';
import { useAuth } from '@contexts/AuthContext';
import { Brand } from './Brand';

/** Shared navigation for the landing page and anonymous demo. */
export function PublicHeader() {
  const { session, loading, signOut } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logout = async () => {
    setBusy(true);
    setError(null);
    try {
      await signOut();
    } catch {
      setError('Unable to sign out. Please try again.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <Stack gap="sm" py="lg">
      <Group
        component="nav"
        justify="space-between"
        aria-label="Main navigation"
      >
        <Brand />
        <Group gap="xs" aria-busy={loading}>
          {session ? (
            <>
              <Button
                variant="default"
                loading={busy}
                onClick={() => void logout()}
              >
                Sign out
              </Button>
              <Button component={Link} to="/dashboard" variant="light">
                Open workspace
              </Button>
            </>
          ) : (
            <>
              <Button
                component={Link}
                to="/login"
                variant="default"
                disabled={loading}
              >
                Sign in
              </Button>
              <Button component={Link} to="/register" disabled={loading}>
                Create account
              </Button>
            </>
          )}
        </Group>
      </Group>
      {error && (
        <Alert color="red" role="alert">
          {error}
        </Alert>
      )}
    </Stack>
  );
}
