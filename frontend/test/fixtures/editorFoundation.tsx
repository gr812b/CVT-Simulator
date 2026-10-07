import { useEffect, useState } from 'react';
import { AuthProvider, useAuth } from '../../src/contexts/AuthContext';
import { QuantityInput } from '../../src/components/quantityInput/QuantityInput';
import { QuantityValidationContext } from '../../src/components/quantityInput/validation';
import { EditorHistoryBoundary, UndoRedoControls } from '../../src/components/editorHistory/EditorHistory';
import { useEditorHistory } from '../../src/components/editorHistory/useEditorHistory';
import { presetUnitPreferences } from '../../src/utils/units';
import { withBeltPreservingPrimaryShaft, primaryShaftRadius } from '../../src/features/physicalLibrary/cvtHardware';
import type { CvtData, BeltChoice } from '../../src/features/physicalLibrary/api';

const belt = (height: number) => ({ name: 'Belt', data: { height_m: height,
  outer_length_m: .95, outer_width_m: .02+2*height*Math.tan(.3), inner_width_m: .02, cord_depth_from_outer_m: .003,
  half_angle_rad: .3, density_kg_per_m3: 1100, length_reference: 'outer' } }) as BeltChoice;
const cvt = { belt: belt(.015), assembly: { geometry: { primary_outer_radius_at_zero_shift_m: .04,
  belt: { height_m: .015 } }, inertias: { belt_density_kg_per_m3: 1100 } } } as CvtData;
function Draft() {
  const auth = useAuth();
  const draft = useEditorHistory({ length: .03302, inertia: .0032202838346490647, name: 'Original', cvt });
  const [invalid, setInvalid] = useState(new Set<string>());
  const [hidden, setHidden] = useState(false);
  const [fail, setFail] = useState(false);
  const [saves, setSaves] = useState(0);
  const [message, setMessage] = useState('');
  const update = <K extends keyof typeof draft.value>(key: K, value: (typeof draft.value)[K]) =>
    draft.setValue(current => ({ ...current, [key]: value }));
  return <EditorHistoryBoundary history={draft.history}>
    <UndoRedoControls history={draft.history} />
    <QuantityValidationContext.Provider value={setInvalid}>
      {!hidden && <QuantityInput label="Test length" draftKey="length" documentPath="/length"
        dimension="length" scope="hardware" value={draft.value.length} min={0} max={1}
        onChange={value => update('length', value)} />}
      <QuantityInput label="Test inertia" draftKey="inertia" scope="hardware" unit="kg·m²"
        value={draft.value.inertia} onChange={value => update('inertia', value)} />
      <label>Name<input value={draft.value.name} onChange={e => update('name', e.target.value)} /></label>
      <button onClick={() => setHidden(!hidden)}>Toggle length visibility</button>
      <button onClick={() => setFail(!fail)}>Toggle failed save</button>
      <button onClick={() => update('cvt', withBeltPreservingPrimaryShaft(draft.value.cvt, belt(.02)))}>Change belt</button>
      <button disabled={invalid.size > 0 || draft.invalidCount > 0} onClick={() => {
        if (draft.history.getSnapshot().invalidCount) return;
        if (fail) { setMessage('Save failed'); return; }
        setSaves(n => n + 1); draft.history.markSaved(draft.value); setInvalid(new Set()); setMessage('Saved');
      }}>Save draft</button>
      <button onClick={() => { draft.history.reset({length:.03302,inertia:.0032202838346490647,name:'Original',cvt});setInvalid(new Set()); }}>Discard draft</button>
      <button onClick={() => void auth.saveUnitPreferences(presetUnitPreferences('si'))}>SI preferences</button>
      <button onClick={() => void auth.saveUnitPreferences(presetUnitPreferences('recommended'))}>Recommended preferences</button>
      <button onClick={() => void auth.signOut()}>Sign out</button>
    </QuantityValidationContext.Provider>
    <output data-testid="state">{JSON.stringify({ value: draft.value, dirty: draft.dirty,
      invalid: draft.invalidCount + invalid.size, saves, message, shaft: primaryShaftRadius(draft.value.cvt),
      preferences:auth.unitPreferences, canUndo:draft.canUndo,canRedo:draft.canRedo })}</output>
    <button data-testid="keyboard-target">Keyboard target</button>
  </EditorHistoryBoundary>;
}
function Gate() {
  const { session, loading } = useAuth();
  useEffect(() => {
    if (!loading && !session) document.body.dataset.signedOut = 'true';
  }, [session, loading]);
  if (loading) return <p>Loading session</p>;
  return session ? <Draft /> : <p>Signed out</p>;
}
export function EditorFoundationFixture() { return <AuthProvider><Gate /></AuthProvider>; }
