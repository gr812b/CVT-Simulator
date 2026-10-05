import { SchoolSelect } from '../../features/community/SchoolSelect';
import { useState } from 'react';
import {
  Alert,
  Badge,
  Container,
  Group,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { useForm } from '@mantine/form';
import { changePassword, updateProfile } from '@api/auth';
import { useAuth } from '@contexts/AuthContext';

export function AccountSettings() {
  const { session, accept } = useAuth();
  const [busy, setBusy] = useState<'profile' | 'password' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const profile = useForm({
    initialValues: {
      display_name: session?.user.display_name ?? '',
      school: session?.user.school ?? '',
    },
    validate: {
      display_name: (value) => (value.trim() ? null : 'Enter your name.'),
    },
  });
  const password = useForm({
    initialValues: { current_password: '', password: '', confirm: '' },
    validate: {
      password: (value) =>
        value.length >= 12 ? null : 'Use at least 12 characters.',
      confirm: (value, values) =>
        value === values.password ? null : 'Passwords do not match.',
    },
  });
  const save = async (
    kind: 'profile' | 'password',
    action: () => ReturnType<typeof updateProfile>,
  ) => {
    setBusy(kind);
    setError(null);
    setMessage(null);
    try {
      accept(await action());
      setMessage(
        kind === 'profile'
          ? 'Profile updated.'
          : 'Password updated. Your other sessions have been signed out.',
      );
      if (kind === 'password') password.reset();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : 'Unable to save changes.',
      );
    } finally {
      setBusy(null);
    }
  };
  return (
    <Container size="sm" py="xl">
      <Stack gap="xl">
        <div>
          <Title order={1}>Account settings</Title>
          <Text c="dimmed">Manage your profile and account security.</Text>
        </div>
        {error && (
          <Alert color="red" role="alert">
            {error}
          </Alert>
        )}
        {message && (
          <Alert color="teal" role="status">
            {message}
          </Alert>
        )}
        <Paper withBorder p="lg">
          <form
            onSubmit={profile.onSubmit((values) =>
              save('profile', () =>
                updateProfile({
                  display_name: values.display_name.trim(),
                  school: values.school.trim(),
                }),
              ),
            )}
          >
            <Stack>
              <Group justify="space-between">
                <Title order={2} size="h3">
                  Profile
                </Title>
                <Badge>Free workspace</Badge>
              </Group>
              <TextInput
                label="Email"
                value={session?.user.email ?? ''}
                readOnly
              />
              <TextInput
                label="Your name"
                autoComplete="name"
                maxLength={100}
                required
                {...profile.getInputProps('display_name')}
              />
              <SchoolSelect
                value={profile.values.school}
                onChange={(value) =>
                  profile.setFieldValue('school', value ?? '')
                }
              />
              <Text size="sm" c="dimmed">
                Free accounts save simulation content publicly.
              </Text>
              <Button
                type="submit"
                loading={busy === 'profile'}
                disabled={busy !== null}
              >
                Save profile
              </Button>
            </Stack>
          </form>
        </Paper>
        <Paper withBorder p="lg">
          <form
            onSubmit={password.onSubmit((values) =>
              save('password', () =>
                changePassword({
                  current_password: values.current_password,
                  password: values.password,
                }),
              ),
            )}
          >
            <Stack>
              <Title order={2} size="h3">
                Change password
              </Title>
              <PasswordInput
                label="Current password"
                autoComplete="current-password"
                required
                {...password.getInputProps('current_password')}
              />
              <PasswordInput
                label="New password"
                description="At least 12 characters."
                autoComplete="new-password"
                maxLength={128}
                required
                {...password.getInputProps('password')}
              />
              <PasswordInput
                label="Confirm new password"
                autoComplete="new-password"
                required
                {...password.getInputProps('confirm')}
              />
              <Button
                type="submit"
                loading={busy === 'password'}
                disabled={busy !== null}
              >
                Update password
              </Button>
            </Stack>
          </form>
        </Paper>
      </Stack>
    </Container>
  );
}
