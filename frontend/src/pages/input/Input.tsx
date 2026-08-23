import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@components/button/Button';
import { ParameterAccordion } from '@components/parameterAccordion/ParameterAccordion';
import { ParameterDescription } from '@components/parameterDescription/ParameterDescription';
import { RampBuilder } from '@components/rampBuilder/RampBuilder';
import { RampPreview } from '@components/rampBuilder/RampPreview';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { useLoading } from '@contexts/LoadingContext';
import { useRunSimulation } from '@hooks/useRunSimulation';
import {
  buildLibraryRunSelection,
  buildRunSetupForVehicle,
  getDefaultRunSetup,
  resolveSimulationCaseFromLibrarySelection,
  updateTuneValues,
  type DefaultRunSetup,
  type ExecutionPresetSummary,
  type LoadCaseSummary,
  type SimulationCaseDocument,
  type TuneSummary,
} from '@api/client';
import { editorToRamp, rampToEditor } from '@utils/rampEditor';
import { DocumentQuantityInput } from './DocumentQuantityInput';
import {
  GROUPS,
  GROUP_TITLES,
  resolveTuneSurface,
  setTuneFieldValue,
  valueForTuneField,
  type ResolvedTuningField,
  type TuningGroup,
} from './tuningSurface';
import Home from '@assets/icons/home.svg?react';
import ArrowUpCircle from '@assets/icons/arrow_up_circle.svg?react';
import ArrowDownCircle from '@assets/icons/arrow_down_circle.svg?react';
import ArrowLeft from '@assets/icons/arrow_left.svg?react';
import PlayOutline from '@assets/icons/play_outline.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import styles from './Input.module.scss';

const expandedState = Object.fromEntries(GROUPS.map((group) => [group, true])) as Record<TuningGroup, boolean>;
const collapsedState = Object.fromEntries(GROUPS.map((group) => [group, false])) as Record<TuningGroup, boolean>;

type CustomLoadCaseSegment = {
  distanceM: number;
  gradeDeg: number;
};

const POUNDS_TO_KG = 0.45359237;

function selectValue<T extends { id: string }>(items: T[], id: string | null): T | null {
  if (id === null) return null;
  return items.find((item) => item.id === id) ?? null;
}

function tuneValuesEqual(a: Record<string, unknown>, b: Record<string, unknown>): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function makeCustomLoadCaseRoadProfile(segments: CustomLoadCaseSegment[]) {
  const normalized = segments
    .map((segment) => ({
      distanceM: Number.isFinite(segment.distanceM) ? Math.max(0, segment.distanceM) : 0,
      gradeDeg: Number.isFinite(segment.gradeDeg) ? segment.gradeDeg : 0,
    }))
    .filter((segment) => segment.distanceM > 0);

  if (normalized.length === 0) {
    return { kind: 'constant_grade', grade_angle_rad: 0 };
  }

  if (normalized.length === 1) {
    return {
      kind: 'constant_grade',
      grade_angle_rad: (normalized[0].gradeDeg * Math.PI) / 180,
    };
  }

  let cumulativeDistanceM = 0;
  return {
    kind: 'piecewise_constant_grade',
    segments: normalized.map((segment) => {
      const startDistanceM = cumulativeDistanceM;
      cumulativeDistanceM += segment.distanceM;
      return {
        start_distance_m: startDistanceM,
        grade_angle_rad: (segment.gradeDeg * Math.PI) / 180,
      };
    }),
  };
}

/**
 * Run setup edits DB tune values only. Engine/CVT hardware/output-system data
 * remain pinned by the released seeded Baja assembly, while load and execution
 * are explicit selectors below. Test/demo account IDs stay in the API boundary.
 */
export const Input = () => {
  const navigate = useNavigate();
  const { isLoading, loadingMessage, setLoading } = useLoading();
  const { runLibrarySetup, runSimulationDocument } = useRunSimulation();
  const [setup, setSetup] = useState<DefaultRunSetup | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<TuningGroup, boolean>>(expandedState);
  const [active, setActive] = useState<string | null>(null);
  const [selectedVehicleAssemblyId, setSelectedVehicleAssemblyId] = useState<string | null>(null);
  const [selectedTuneId, setSelectedTuneId] = useState<string | null>(null);
  const [selectedLoadCaseId, setSelectedLoadCaseId] = useState<string | null>(null);
  const [selectedExecutionPresetId, setSelectedExecutionPresetId] = useState<string | null>(null);
  const [tuneValues, setTuneValues] = useState<Record<string, unknown>>({});
  const [savedTuneValues, setSavedTuneValues] = useState<Record<string, unknown>>({});
  const [useCustomLoadCase, setUseCustomLoadCase] = useState(false);
  const [customLoadCaseSegments, setCustomLoadCaseSegments] = useState<CustomLoadCaseSegment[]>([
    { distanceM: 60, gradeDeg: 0 },
    { distanceM: 90, gradeDeg: 20 },
  ]);
  const [useCustomVehicleMass, setUseCustomVehicleMass] = useState(false);
  const [customVehicleMassKg, setCustomVehicleMassKg] = useState(300);
  const [customVehicleMassUnit, setCustomVehicleMassUnit] = useState<'kg' | 'lb'>('kg');

  const refreshSetup = useCallback(async () => {
    setLoading(true, 'Loading seeded Baja run setup...');
    setSetupError(null);
    try {
      const next = await getDefaultRunSetup();
      setSetup(next);
      setSelectedVehicleAssemblyId(next.selectedVehicleAssembly.id);
      setSelectedTuneId(next.selectedTune?.id ?? null);
      setSelectedLoadCaseId(next.selectedLoadCase?.id ?? null);
      setSelectedExecutionPresetId(next.selectedExecutionPreset?.id ?? null);
      setTuneValues(next.selectedTune?.values ?? {});
      setSavedTuneValues(next.selectedTune?.values ?? {});
    } catch (error) {
      setSetupError(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  }, [setLoading]);

  useEffect(() => { void refreshSetup(); }, [refreshSetup]);

  const selectedVehicleAssembly = useMemo(() => selectValue(setup?.vehicleAssemblies ?? [], selectedVehicleAssemblyId), [selectedVehicleAssemblyId, setup]);
  const selectedTune = useMemo<TuneSummary | null>(() => selectValue(setup?.tunes ?? [], selectedTuneId), [selectedTuneId, setup]);
  const selectedLoadCase = useMemo<LoadCaseSummary | null>(() => selectValue(setup?.loadCases ?? [], selectedLoadCaseId), [selectedLoadCaseId, setup]);
  const selectedExecutionPreset = useMemo<ExecutionPresetSummary | null>(() => selectValue(setup?.executionPresets ?? [], selectedExecutionPresetId), [selectedExecutionPresetId, setup]);
  const fields = useMemo(() => resolveTuneSurface(setup?.tuningParameters ?? []), [setup]);
  const activeField = fields.find((field) => field.key === active) ?? null;
  const hasUnsavedTuneChanges = selectedTune !== null && !tuneValuesEqual(tuneValues, savedTuneValues);

  const chooseVehicleAssembly = useCallback(async (nextId: string) => {
    if (setup === null || nextId === selectedVehicleAssemblyId) return;
    if (hasUnsavedTuneChanges && !window.confirm('Switching vehicle baselines will reload the tune list. Discard unsaved visible tune changes?')) {
      return;
    }

    setLoading(true, 'Loading selected Baja baseline...');
    setSetupError(null);
    try {
      const next = await buildRunSetupForVehicle(
        setup.vehicleAssemblies,
        nextId,
        setup.accountId,
        setup.createdByUserId,
      );
      setSetup(next);
      setSelectedVehicleAssemblyId(next.selectedVehicleAssembly.id);
      setSelectedTuneId(next.selectedTune?.id ?? null);
      setSelectedLoadCaseId(next.selectedLoadCase?.id ?? selectedLoadCaseId);
      setSelectedExecutionPresetId(next.selectedExecutionPreset?.id ?? selectedExecutionPresetId);
      setTuneValues(next.selectedTune?.values ?? {});
      setSavedTuneValues(next.selectedTune?.values ?? {});
    } catch (error) {
      setSetupError(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  }, [hasUnsavedTuneChanges, selectedExecutionPresetId, selectedLoadCaseId, selectedVehicleAssemblyId, setLoading, setup]);

  const chooseTune = useCallback((nextId: string) => {
    const nextTune = setup?.tunes.find((tune) => tune.id === nextId) ?? null;
    setSelectedTuneId(nextTune?.id ?? null);
    setTuneValues(nextTune?.values ?? {});
    setSavedTuneValues(nextTune?.values ?? {});
  }, [setup?.tunes]);

  const updateField = useCallback((field: ResolvedTuningField, next: unknown) => {
    setTuneValues((current) => setTuneFieldValue(current, field, next));
  }, []);

  const saveTune = useCallback(async (): Promise<TuneSummary | null> => {
    if (selectedTune === null) return null;
    setLoading(true, 'Saving tune values...');
    try {
      const saved = await updateTuneValues(selectedTune.id, tuneValues);
      setSavedTuneValues(saved.values);
      setSetup((current) => current === null ? current : {
        ...current,
        tunes: current.tunes.map((tune) => tune.id === saved.id ? saved : tune),
        selectedTune: current.selectedTune?.id === saved.id ? saved : current.selectedTune,
      });
      return saved;
    } finally {
      setLoading(false);
    }
  }, [selectedTune, setLoading, tuneValues]);

  const resetTune = useCallback(() => {
    if (!window.confirm('Reset the visible tune fields to the last saved tune values?')) return;
    setTuneValues(savedTuneValues);
  }, [savedTuneValues]);

  const run = useCallback(async () => {
    if (setup === null) return;
    if (selectedTune !== null && hasUnsavedTuneChanges) await saveTune();

    const selection = buildLibraryRunSelection(setup, {
      vehicleAssemblyId: selectedVehicleAssemblyId ?? undefined,
      tuneId: selectedTuneId,
      loadCaseId: selectedLoadCaseId,
      executionPresetId: selectedExecutionPresetId,
    });

    if (useCustomLoadCase) {
      const resolvedDocument = await resolveSimulationCaseFromLibrarySelection(selection);
      const document = JSON.parse(JSON.stringify(resolvedDocument)) as Record<string, unknown>;
      const customRoadProfile = makeCustomLoadCaseRoadProfile(customLoadCaseSegments);
      const shaftBoundaries = typeof document.shaft_boundaries === 'object' && document.shaft_boundaries !== null
        ? document.shaft_boundaries as Record<string, unknown>
        : null;
      const secondaryBoundary = shaftBoundaries !== null && typeof shaftBoundaries.secondary === 'object' && shaftBoundaries.secondary !== null
        ? shaftBoundaries.secondary as Record<string, unknown>
        : null;
      if (secondaryBoundary !== null) {
        secondaryBoundary.road_profile = customRoadProfile;
      }

      // Keep V1 compatibility alias in sync when present.
      const previousOutputBoundary = typeof document.output_boundary === 'object' && document.output_boundary !== null
        ? document.output_boundary as Record<string, unknown>
        : null;
      if (previousOutputBoundary !== null) {
        previousOutputBoundary.road_profile = customRoadProfile;
      }

      if (useCustomVehicleMass) {
        if (!Number.isFinite(customVehicleMassKg) || customVehicleMassKg <= 0) {
          alert('Custom vehicle mass must be a positive number.');
          return;
        }

        const validMass = customVehicleMassUnit === 'lb'
          ? customVehicleMassKg * POUNDS_TO_KG
          : customVehicleMassKg;
        if (secondaryBoundary !== null && typeof secondaryBoundary.vehicle === 'object' && secondaryBoundary.vehicle !== null) {
          (secondaryBoundary.vehicle as Record<string, unknown>).mass_kg = validMass;
        }
        if (previousOutputBoundary !== null && typeof previousOutputBoundary.vehicle === 'object' && previousOutputBoundary.vehicle !== null) {
          (previousOutputBoundary.vehicle as Record<string, unknown>).mass_kg = validMass;
        }
      }

      await runSimulationDocument(document as unknown as SimulationCaseDocument);
      return;
    }

    await runLibrarySetup(selection);
  }, [customLoadCaseSegments, customVehicleMassKg, customVehicleMassUnit, hasUnsavedTuneChanges, runLibrarySetup, runSimulationDocument, saveTune, selectedExecutionPresetId, selectedLoadCaseId, selectedTune, selectedTuneId, selectedVehicleAssemblyId, setup, useCustomLoadCase, useCustomVehicleMass]);

  if (setup === null) {
    return (
      <div className={styles.input}>
        <LoadingOverlay isVisible={isLoading} message={loadingMessage} />
        <div className={styles.parameterInformationContainer}>
          <ParameterDescription name="Loading Baja baseline" description={setupError ?? 'Loading the seeded database-backed run setup…'} />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.input}>
      <LoadingOverlay isVisible={isLoading} message={loadingMessage} />
      <div className={styles.topBar}>
        <div className={styles.navButtons}>
          <Button text="Home" icon={Home} onClick={() => navigate('/')} />
          <Button text="Library" icon={ArrowLeft} onClick={() => navigate('/dashboard')} />
        </div>
        <div className={styles.sessionInfo} title={selectedVehicleAssembly?.description ?? setup.selectedVehicleAssembly.description ?? ''}>
          <span className={styles.selectedSetName}>Baja Run Setup</span>
          <span className={styles.changesBadge}>
            <span className={styles.changeIndicator} />
            <span>{hasUnsavedTuneChanges ? 'Unsaved tune changes' : 'Seeded Baja baseline'}</span>
          </span>
        </div>
        <div className={styles.topBarSpacer} />
      </div>

      <div className={styles.inputGrid}>
        <div className={styles.parameterInputContainer}>
          <section className={styles.setupCard}>
            <h2>Baseline and simulation load</h2>
            <label className={styles.selectField}>
              <span>Vehicle baseline</span>
              <select value={selectedVehicleAssemblyId ?? ''} onChange={(event) => void chooseVehicleAssembly(event.target.value)} disabled={setup.vehicleAssemblies.length === 0}>
                {setup.vehicleAssemblies.map((assembly) => <option key={assembly.id} value={assembly.id}>{assembly.name}{assembly.isDefault ? ' · Default' : ''}</option>)}
              </select>
            </label>
            <label className={styles.selectField}>
              <span>Tune being edited</span>
              <select value={selectedTuneId ?? ''} onChange={(event) => chooseTune(event.target.value)} disabled={setup.tunes.length === 0}>
                {setup.tunes.map((tune) => <option key={tune.id} value={tune.id}>{tune.name}</option>)}
              </select>
            </label>
            <label className={styles.selectField}>
              <span>Load case</span>
              <select value={selectedLoadCaseId ?? ''} onChange={(event) => setSelectedLoadCaseId(event.target.value || null)} disabled={setup.loadCases.length === 0}>
                {setup.loadCases.map((loadCase) => <option key={loadCase.id} value={loadCase.id}>{loadCase.name}</option>)}
              </select>
            </label>
            <label className={styles.selectField}>
              <span>Execution preset</span>
              <select value={selectedExecutionPresetId ?? ''} onChange={(event) => setSelectedExecutionPresetId(event.target.value || null)} disabled={setup.executionPresets.length === 0}>
                {setup.executionPresets.map((preset) => <option key={preset.id} value={preset.id}>{preset.name}</option>)}
              </select>
            </label>

            <label className={styles.selectField}>
              <span>Custom run load case</span>
              <label className={styles.customLoadCaseCheckbox}>
                <input type="checkbox" checked={useCustomLoadCase} onChange={(event) => setUseCustomLoadCase(event.target.checked)} />
                Use a one-off custom road profile for this run only
              </label>
            </label>

            {useCustomLoadCase && (
              <div className={styles.setupCard} style={{ width: '100%', marginBottom: 0 }}>
                <h3>Road profile</h3>
                <label className={styles.selectField}>
                  <span>Vehicle mass override</span>
                  <label className={styles.customLoadCaseCheckbox}>
                    <input type="checkbox" checked={useCustomVehicleMass} onChange={(event) => setUseCustomVehicleMass(event.target.checked)} />
                    Override vehicle mass for this run only
                  </label>
                </label>
                {useCustomVehicleMass && (
                  <div className={styles.customMassRow}>
                    <label className={`${styles.selectField} ${styles.customMassField}`}>
                      <span>Unit</span>
                      <select value={customVehicleMassUnit} onChange={(event) => setCustomVehicleMassUnit(event.target.value === 'lb' ? 'lb' : 'kg')}>
                        <option value="kg">kg</option>
                        <option value="lb">lb</option>
                      </select>
                    </label>
                    <label className={`${styles.selectField} ${styles.customMassField}`}>
                      <span>Mass ({customVehicleMassUnit})</span>
                      <input
                        type="number"
                        min={0}
                        step={1}
                        value={customVehicleMassKg}
                        onChange={(event) => setCustomVehicleMassKg(Number(event.target.value))}
                      />
                    </label>
                  </div>
                )}

                {customLoadCaseSegments.map((segment, index) => (
                  <div key={`${index}-${segment.distanceM}-${segment.gradeDeg}`} className={styles.customSegmentRow}>
                    <label className={`${styles.selectField} ${styles.customLoadCaseField}`}>
                      <span>Distance (m)</span>
                      <input
                        type="number"
                        min={0}
                        step={0.1}
                        value={segment.distanceM}
                        onChange={(event) => setCustomLoadCaseSegments((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, distanceM: Number(event.target.value) } : item))}
                      />
                    </label>
                    <label className={`${styles.selectField} ${styles.customLoadCaseField}`}>
                      <span>Grade (°)</span>
                      <input
                        type="number"
                        step={0.1}
                        value={segment.gradeDeg}
                        onChange={(event) => setCustomLoadCaseSegments((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, gradeDeg: Number(event.target.value) } : item))}
                      />
                    </label>
                    <Button text="Remove" icon={ArrowLeft} onClick={() => setCustomLoadCaseSegments((current) => current.filter((_, itemIndex) => itemIndex !== index))} disabled={customLoadCaseSegments.length === 1} />
                  </div>
                ))}
                <Button text="Add segment" icon={ArrowDownCircle} onClick={() => setCustomLoadCaseSegments((current) => [...current, { distanceM: 25, gradeDeg: 0 }])} />
                <p className={styles.helperText}>This custom profile only affects the next run. It is not saved to the library or database.</p>
              </div>
            )}

            <p className={styles.helperText}>Engine and CVT hardware stay shared by the seeded Baja baselines. The vehicle dropdown changes the pinned output-system mass; the boxes below update the selected CVT tune only.</p>
          </section>

          {GROUPS.map((group) => (
            <ParameterAccordion key={group} title={GROUP_TITLES[group]} isExpanded={expanded[group]} onToggle={() => setExpanded((current) => ({ ...current, [group]: !current[group] }))}>
              {fields.filter((field) => field.group === group).map((field) => {
                const value = valueForTuneField(field, tuneValues);
                const original = valueForTuneField(field, savedTuneValues);
                const changed = JSON.stringify(value) !== JSON.stringify(original);
                if (field.kind === 'ramp') {
                  return (
                    <div key={field.key} onFocus={() => setActive(field.key)}>
                      <RampBuilder value={rampToEditor(value)} hasChanged={changed} onChange={(next) => updateField(field, editorToRamp(next))} />
                    </div>
                  );
                }
                const numeric = numberValue(value);
                return numeric === null ? null : (
                  <DocumentQuantityInput
                    key={field.key}
                    label={field.label}
                    valueSi={numeric}
                    dimension={field.dimension}
                    canonicalUnit={field.canonicalUnit}
                    minimum={field.minimum}
                    hasChanged={changed}
                    onFocus={() => setActive(field.key)}
                    onChangeSi={(next) => updateField(field, next)}
                  />
                );
              })}
            </ParameterAccordion>
          ))}
        </div>

        <div className={styles.parameterInformationContainer}>
          <ParameterDescription
            name={setupError ?? activeField?.label ?? 'No tune parameter selected'}
            description={setupError ?? activeField?.description ?? 'Click a tune input to see what DB tune key it edits. Vehicle baseline, load case, and execution are selected above; engine/CVT hardware stay pinned by the seeded baseline.'}
            img={activeField?.image}
          />
          {activeField?.kind === 'ramp' && <RampPreview config={rampToEditor(valueForTuneField(activeField, tuneValues))} />}
          <section className={styles.summaryCard}>
            <h2>Current DB selection</h2>
            <dl>
              <dt>Vehicle</dt><dd>{selectedVehicleAssembly?.name ?? setup.selectedVehicleAssembly.name}</dd>
              <dt>Tune</dt><dd>{selectedTune?.name ?? 'None'}</dd>
              <dt>Load case</dt><dd>{selectedLoadCase?.name ?? 'None'}</dd>
              <dt>Execution</dt><dd>{selectedExecutionPreset?.name ?? 'None'}</dd>
            </dl>
          </section>
        </div>

        <div className={styles.inputButtonsContainer}>
          <Button text="Expand All" icon={ArrowDownCircle} onClick={() => setExpanded(expandedState)} />
          <Button text="Collapse All" icon={ArrowUpCircle} iconSide="right" onClick={() => setExpanded(collapsedState)} />
        </div>
        <div className={styles.nextButtonContainer}>
          <Button text="Reset Tune" icon={ArrowLeft} disabled={!hasUnsavedTuneChanges} onClick={resetTune} />
          <Button text="Save Tune" icon={Edit} disabled={selectedTune === null || !hasUnsavedTuneChanges} onClick={() => void saveTune()} />
          <Button text="Run" icon={PlayOutline} disabled={setupError !== null || selectedTune === null} onClick={() => void run()} />
        </div>
      </div>
    </div>
  );
};
