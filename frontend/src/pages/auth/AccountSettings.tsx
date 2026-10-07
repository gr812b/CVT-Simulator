import { SchoolSelect } from '../../features/community/SchoolSelect';
import { useCallback, useEffect, useRef, useState } from 'react';
import { UnitPreferenceFields } from './UnitPreferenceFields';
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
import { Modal } from '@components/modal/Modal';
import { EditorHistoryBoundary, UndoRedoControls } from '@components/editorHistory/EditorHistory';
import { useEditorHistory } from '@components/editorHistory/useEditorHistory';
import { useForm } from '@mantine/form';
import { changePassword, updateProfile } from '@api/auth';
import { useAuth } from '@contexts/AuthContext';
import { useBeforeUnload, useBlocker } from 'react-router-dom';
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
  const unitDraft = useEditorHistory<UnitPreferences>(() =>
    normalizeUnitPreferences(session?.user.unit_preferences),
  );
  const { history: unitHistory, value: units, setValue: setUnits, dirty: unitsDirty } = unitDraft;
  const persistedUnits = JSON.stringify(normalizeUnitPreferences(session?.user.unit_preferences));
  const [discardUnitsOpen, setDiscardUnitsOpen] = useState(false);
  const unitsBlocker = useBlocker(
    useCallback(() => unitsDirty, [unitsDirty]),
  );
  useBeforeUnload(
    useCallback((event) => {
      if (!unitsDirty) return;
      event.preventDefault();
      event.returnValue = '';
    }, [unitsDirty]),
  );
  useEffect(() => {
    if (unitsBlocker.state === 'blocked') setDiscardUnitsOpen(true);
  }, [unitsBlocker.state]);
  const savedUnits = () => normalizeUnitPreferences(JSON.parse(persistedUnits));
  const discardUnits = (leave = false) => {
    unitHistory.reset(savedUnits());
    setDiscardUnitsOpen(false);
    if (unitsBlocker.state === 'blocked') {
      if (leave) unitsBlocker.proceed();
      else unitsBlocker.reset();
    }
  };
  const priorPreferences = useRef({ owner: session?.user.id, value: persistedUnits });
  useEffect(() => {
    const previous = priorPreferences.current;
    const owner = session?.user.id;
    // A focus refresh may return a new object without changing any preferences.
    // Do not erase unsaved selections in Account Settings on that refresh.
    const next = normalizeUnitPreferences(JSON.parse(persistedUnits));
    const snapshot = unitHistory.getSnapshot();
    if (previous.owner !== owner || !snapshot.dirty) unitHistory.reset(next);
    else if (JSON.stringify(snapshot.value) === persistedUnits)
      unitHistory.markSaved(next);
    priorPreferences.current = { owner, value: persistedUnits };
  }, [persistedUnits, session?.user.id, unitHistory]);
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
      unitHistory.markSaved(units);
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
        <EditorHistoryBoundary history={unitHistory} disabled={busy !== null}>
          <Paper withBorder p="lg">
            <Stack>
              <div>
                <Group justify="space-between" align="center">
                  <Title order={2} size="h3">Display units</Title>
                  {unitsDirty && <Badge color="orange">Unsaved changes</Badge>}
                </Group>
              <Text size="sm" c="dimmed" mt="xs">
                These are personal display preferences shared across devices. Changes stay local to this form until you save them; CINDER documents and raw results remain canonical SI.
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
            <UnitPreferenceFields scope="hardware" value={units} onChange={setUnits} />
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
            <UnitPreferenceFields scope="vehicle" value={units} onChange={setUnits} />
            <UnitPreferenceFields scope="course" value={units} onChange={setUnits} />
            <Title order={3} size="h4">Outputs & playback</Title>
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              <Select label="Lengths" value={units.output_length} allowDeselect={false}
                data={['m', 'ft', 'mm', 'in']}
                onChange={(value) => value && patchUnits('output_length', value as UnitPreferences['output_length'])} />
              <Select label="Speed" value={units.output_speed} allowDeselect={false}
                data={['km/h', 'm/s', 'mph']}
                onChange={(value) => value && patchUnits('output_speed', value as UnitPreferences['output_speed'])} />
            </SimpleGrid>
            <UnitPreferenceFields scope="output" value={units} onChange={setUnits} />
            {unitsDirty && (
              <UndoRedoControls history={unitHistory} disabled={busy !== null} />
            )}
            <Group justify="flex-end">
              <Button
                variant="default"
                disabled={busy !== null || !unitsDirty}
                onClick={() => discardUnits()}
              >
                Discard changes
              </Button>
              <Button
                loading={busy === 'units'}
                disabled={busy !== null || !unitsDirty}
                onClick={() => void saveUnits()}
              >
                Save changes
              </Button>
            </Group>
            </Stack>
          </Paper>
        </EditorHistoryBoundary>
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
        <Modal
          opened={discardUnitsOpen}
          onClose={() => {
            setDiscardUnitsOpen(false);
            if (unitsBlocker.state === 'blocked') unitsBlocker.reset();
          }}
          title="Discard display-unit changes?"
          closeOnClickOutside={false}
        >
          <Stack>
            <Text>
              Your display-unit selections have not been saved. Leave this page and discard them?
            </Text>
            <Group justify="flex-end">
              <Button
                variant="default"
                onClick={() => {
                  setDiscardUnitsOpen(false);
                  if (unitsBlocker.state === 'blocked') unitsBlocker.reset();
                }}
              >
                Keep editing
              </Button>
              <Button color="red" onClick={() => discardUnits(true)}>
                Discard and leave
              </Button>
            </Group>
          </Stack>
        </Modal>
      </Stack>
    </Container>
  );
}
