import { SchoolSelect } from '../../features/community/SchoolSelect';
import { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Container,
  Group,
  Paper,
  PasswordInput,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { ActionButton as Button } from '@components/button/ActionButton';
import { useForm } from '@mantine/form';
import { changePassword, updateProfile } from '@api/auth';
import { useAuth } from '@contexts/AuthContext';
import {
  normalizeUnitPreferences,
  presetUnitPreferences,
  type UnitPreferences,
  type UnitPreset,
} from '@utils/units';

export function AccountSettings() {
  const { session, accept, saveUnitPreferences } = useAuth();
  const [busy, setBusy] = useState<'profile' | 'password' | 'units' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [units, setUnits] = useState<UnitPreferences>(() =>
    normalizeUnitPreferences(session?.user.unit_preferences),
  );
  useEffect(() => {
    setUnits(normalizeUnitPreferences(session?.user.unit_preferences));
  }, [session?.user.unit_preferences]);
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
        value.length >= 8 ? null : 'Use at least 8 characters.',
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
  const saveUnits = async () => {
    setBusy('units');
    setError(null);
    setMessage(null);
    try {
      await saveUnitPreferences(units);
      setMessage('Unit preferences updated. Stored configurations and results remain unchanged in SI.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to save unit preferences.');
    } finally {
      setBusy(null);
    }
  };
  const patchUnits = <K extends keyof UnitPreferences>(key: K, value: UnitPreferences[K]) =>
    setUnits((current) => ({ ...current, [key]: value }));
  return (
    <Container size="sm" py="xl">
      <Stack gap="xl">
        <div>
          <Title order={1}>Account settings</Title>
          <Text c="dimmed">Manage your profile, units and account security.</Text>
        </div>
        {error && <Alert color="red" role="alert">{error}</Alert>}
        {message && <Alert color="teal" role="status">{message}</Alert>}
        <Paper withBorder p="lg">
          <form onSubmit={profile.onSubmit((values) =>
            save('profile', () => updateProfile({
              display_name: values.display_name.trim(),
              school: values.school.trim(),
            }))
          )}>
            <Stack>
              <Group justify="space-between">
                <Title order={2} size="h3">Profile</Title>
                <Badge>Free workspace</Badge>
              </Group>
              <TextInput label="Email" value={session?.user.email ?? ''} readOnly />
              <TextInput label="Your name" autoComplete="name" maxLength={100} required
                {...profile.getInputProps('display_name')} />
              <SchoolSelect value={profile.values.school}
                onChange={(value) => profile.setFieldValue('school', value ?? '')} />
              <Text size="sm" c="dimmed">Free accounts save simulation content publicly.</Text>
              <Button type="submit" loading={busy === 'profile'} disabled={busy !== null}>Save profile</Button>
            </Stack>
          </form>
        </Paper>
        <Paper withBorder p="lg">
          <Stack>
            <div>
              <Title order={2} size="h3">Display units</Title>
              <Text size="sm" c="dimmed" mt="xs">
                These are personal display preferences shared across devices. CINDER documents and raw results stay in canonical SI, so changing units does not change or dirty saved work.
              </Text>
            </div>
            <Select
              label="Preset"
              value={units.preset}
              allowDeselect={false}
              data={[
                { value: 'recommended', label: 'Recommended · inches for CVT hardware, grams, metres, km/h' },
                { value: 'metric', label: 'Metric workshop · millimetres, grams, metres, km/h' },
                { value: 'si', label: 'Strict SI · metres, kilograms, m/s' },
                { value: 'imperial', label: 'Imperial · inches/feet, ounces/pounds, mph' },
              ]}
              onChange={(value) => value && setUnits(presetUnitPreferences(value as UnitPreset))}
            />
            <Title order={3} size="h4">Hardware inputs</Title>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <Select label="Lengths" value={units.hardware_length} allowDeselect={false}
                data={['in', 'mm', 'm']}
                onChange={(value) => value && patchUnits('hardware_length', value as UnitPreferences['hardware_length'])} />
              <Select label="Component / tip masses" value={units.component_mass} allowDeselect={false}
                data={['g', 'kg', 'oz']}
                onChange={(value) => value && patchUnits('component_mass', value as UnitPreferences['component_mass'])} />
            </SimpleGrid>
            <Title order={3} size="h4">Vehicle & course inputs</Title>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <Select label="Vehicle lengths" value={units.vehicle_length} allowDeselect={false}
                data={['m', 'ft', 'in']}
                onChange={(value) => value && patchUnits('vehicle_length', value as UnitPreferences['vehicle_length'])} />
              <Select label="Vehicle mass" value={units.vehicle_mass} allowDeselect={false}
                data={['kg', 'lb']}
                onChange={(value) => value && patchUnits('vehicle_mass', value as UnitPreferences['vehicle_mass'])} />
              <Select label="Course lengths" value={units.course_length} allowDeselect={false}
                data={['m', 'ft']}
                onChange={(value) => value && patchUnits('course_length', value as UnitPreferences['course_length'])} />
              <Select label="Speed" value={units.speed} allowDeselect={false}
                data={['km/h', 'm/s', 'mph']}
                onChange={(value) => value && patchUnits('speed', value as UnitPreferences['speed'])} />
            </SimpleGrid>
            <Title order={3} size="h4">Outputs & playback</Title>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <Select label="Lengths" value={units.output_length} allowDeselect={false}
                data={['m', 'ft', 'mm', 'in']}
                onChange={(value) => value && patchUnits('output_length', value as UnitPreferences['output_length'])} />
              <Select label="Speed" value={units.output_speed} allowDeselect={false}
                data={['km/h', 'm/s', 'mph']}
                onChange={(value) => value && patchUnits('output_speed', value as UnitPreferences['output_speed'])} />
            </SimpleGrid>
            <Button loading={busy === 'units'} disabled={busy !== null} onClick={() => void saveUnits()}>
              Save unit preferences
            </Button>
          </Stack>
        </Paper>
        <Paper withBorder p="lg">
          <form onSubmit={password.onSubmit((values) =>
            save('password', () => changePassword({
              current_password: values.current_password,
              password: values.password,
            }))
          )}>
            <Stack>
              <Title order={2} size="h3">Change password</Title>
              <PasswordInput label="Current password" autoComplete="current-password" required
                {...password.getInputProps('current_password')} />
              <PasswordInput label="New password" description="At least 8 characters."
                autoComplete="new-password" maxLength={128} required
                {...password.getInputProps('password')} />
              <PasswordInput label="Confirm new password" autoComplete="new-password" required
                {...password.getInputProps('confirm')} />
              <Button type="submit" loading={busy === 'password'} disabled={busy !== null}>Update password</Button>
            </Stack>
          </form>
        </Paper>
      </Stack>
    </Container>
  );
}
