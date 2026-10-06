import { SchoolSelect } from '../../features/community/SchoolSelect';
import { Brand } from '@components/appShell/Brand';
import { useEffect, useState } from 'react';
import {
  Alert,
  Anchor,
  Container,
  Divider,
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
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import * as auth from '@api/auth';
import { useAuth } from '@contexts/AuthContext';

type Mode = 'login' | 'register' | 'forgot' | 'reset';
const headings: Record<Mode, string> = {
  login: 'Welcome back',
  register: 'Create your workspace',
  forgot: 'Reset your password',
  reset: 'Choose a new password',
};

export function AuthPage({ mode }: { mode: Mode }) {
  const { session, accept } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [token] = useState(() => {
    const value =
      new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '';
    return value;
  });
  useEffect(() => {
    if (token) window.history.replaceState(null, '', window.location.pathname);
  }, [token]);
  const form = useForm({
    initialValues: {
      email: '',
      password: '',
      display_name: '',
      school: '',
      confirm: '',
    },
    validate: {
      email: (value) =>
        mode === 'reset' || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
          ? null
          : 'Enter a valid email address.',
      display_name: (value) =>
        mode !== 'register' || value.trim().length > 0
          ? null
          : 'Enter your name.',
      password: (value) =>
        mode === 'forgot' ||
        (mode === 'login' ? value.length > 0 : value.length >= 8)
          ? null
          : 'Use at least 8 characters.',
      confirm: (value, values) =>
        !['register', 'reset'].includes(mode) || value === values.password
          ? null
          : 'Passwords do not match.',
    },
  });
  const requested = new URLSearchParams(location.search).get('next');
  const next =
    requested?.startsWith('/') &&
    !requested.startsWith('//') &&
    !requested.includes('\\') &&
    !/^\/(login|register|reset-password|forgot-password)/.test(requested)
      ? requested
      : '/dashboard';
  if (session && (mode === 'login' || mode === 'register'))
    return <Navigate to={next} replace />;
  const submit = form.onSubmit(async (values) => {
    setBusy(true);
    setError(null);
    try {
      if (mode === 'forgot')
        setMessage(
          (await auth.forgotPassword({ email: values.email })).message,
        );
      else if (mode === 'reset')
        setMessage(
          (await auth.resetPassword({ token, password: values.password }))
            .message,
        );
      else {
        const result =
          mode === 'register'
            ? await auth.register({
                email: values.email,
                password: values.password,
                display_name: values.display_name.trim(),
                school: values.school.trim(),
              })
            : await auth.login({
                email: values.email,
                password: values.password,
              });
        accept(result);
        navigate(next, { replace: true });
      }
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to complete your request.',
      );
    } finally {
      setBusy(false);
    }
  });
  return (
    <Container size={440} py={64}>
      <Brand />
      <Title mt="xl" order={1}>
        {headings[mode]}
      </Title>
      <Text c="dimmed" mt="sm" mb="xl">
        {mode === 'register'
          ? 'A free, personal space for your CVT designs and simulation runs.'
          : 'Design, simulate, and understand your drivetrain.'}
      </Text>
      <Paper withBorder p="xl" radius="lg">
        {message ? (
          <Stack>
            <Alert color="teal" role="status">
              {message}
            </Alert>
            <Button component={Link} to="/login">
              Back to sign in
            </Button>
          </Stack>
        ) : (
          <form onSubmit={submit}>
            <Stack>
              {error && (
                <Alert color="red" role="alert">
                  {error}
                </Alert>
              )}
              {mode === 'reset' && !token && (
                <Alert color="yellow">
                  Open the link in your reset email, or{' '}
                  <Anchor component={Link} to="/forgot-password">
                    request a new one
                  </Anchor>
                  .
                </Alert>
              )}
              {mode === 'register' && (
                <TextInput
                  label="Your name"
                  autoComplete="name"
                  maxLength={100}
                  required
                  {...form.getInputProps('display_name')}
                />
              )}
              {mode === 'register' && (
                <>
                  <SchoolSelect
                    value={form.values.school}
                    onChange={(value) =>
                      form.setFieldValue('school', value ?? '')
                    }
                  />
                  <Text size="sm" c="dimmed">
                    Free accounts save configurations, load cases, tunes and
                    runs publicly. Your display name and school appear in the
                    public directory. Your email remains private.
                  </Text>
                </>
              )}
              {mode !== 'reset' && (
                <TextInput
                  label="Email"
                  type="email"
                  autoComplete="email"
                  required
                  {...form.getInputProps('email')}
                />
              )}
              {mode !== 'forgot' && (
                <PasswordInput
                  label={mode === 'reset' ? 'New password' : 'Password'}
                  description={
                    mode === 'login'
                      ? undefined
                      : 'At least 8 characters. Spaces and passphrases are welcome.'
                  }
                  autoComplete={
                    mode === 'login' ? 'current-password' : 'new-password'
                  }
                  maxLength={128}
                  required
                  {...form.getInputProps('password')}
                />
              )}
              {['register', 'reset'].includes(mode) && (
                <PasswordInput
                  label="Confirm password"
                  autoComplete="new-password"
                  required
                  {...form.getInputProps('confirm')}
                />
              )}
              <Button
                type="submit"
                loading={busy}
                disabled={mode === 'reset' && !token}
              >
                {mode === 'register'
                  ? 'Create account'
                  : mode === 'forgot'
                    ? 'Send reset link'
                    : mode === 'reset'
                      ? 'Update password'
                      : 'Sign in'}
              </Button>
              {mode === 'login' && (
                <Anchor component={Link} to="/forgot-password" size="sm">
                  Forgot password?
                </Anchor>
              )}
            </Stack>
          </form>
        )}
        <Divider my="lg" />
        <Group justify="center" gap="xs">
          <Text size="sm">
            {mode === 'register'
              ? 'Already have an account?'
              : 'New to CINDER?'}
          </Text>
          <Anchor
            component={Link}
            to={mode === 'register' ? '/login' : '/register'}
            size="sm"
          >
            {mode === 'register' ? 'Sign in' : 'Create account'}
          </Anchor>
        </Group>
      </Paper>
    </Container>
  );
}
