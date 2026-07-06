import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@components/button/Button';
import { ParameterAccordion } from '@components/parameterAccordion/ParameterAccordion';
import { ParameterDescription } from '@components/parameterDescription/ParameterDescription';
import { RampBuilder } from '@components/rampBuilder/RampBuilder';
import { RampPreview } from '@components/rampBuilder/RampPreview';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { useLoading } from '@contexts/LoadingContext';
import { useSimulationCase } from '@contexts/SimulationCaseContext';
import { validateSimulationCase } from '@api/client';
import { getValueAtJsonPointer } from '@utils/jsonPointer';
import { editorToRamp, rampToEditor } from '@utils/rampEditor';
import { useRunSimulation } from '@hooks/useRunSimulation';
import { DocumentQuantityInput } from './DocumentQuantityInput';
import { GROUPS, GROUP_TITLES, resolveSurface, type ResolvedTuningField, type TuningGroup } from './tuningSurface';
import Home from '@assets/icons/home.svg?react';
import ArrowUpCircle from '@assets/icons/arrow_up_circle.svg?react';
import ArrowDownCircle from '@assets/icons/arrow_down_circle.svg?react';
import ArrowLeft from '@assets/icons/arrow_left.svg?react';
import PlayOutline from '@assets/icons/play_outline.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import styles from './Input.module.scss';

const expandedState = Object.fromEntries(GROUPS.map((group) => [group, true])) as Record<TuningGroup, boolean>;
const collapsedState = Object.fromEntries(GROUPS.map((group) => [group, false])) as Record<TuningGroup, boolean>;

export const Input = () => {
  const navigate = useNavigate(); const { isLoading, loadingMessage, setLoading } = useLoading(); const { document, source, editorSchema, validation, ensureReady, loadPreset, setValueAtPath, setValidation } = useSimulationCase(); const { runSimulation } = useRunSimulation();
  const [expanded, setExpanded] = useState<Record<TuningGroup, boolean>>(expandedState); const [active, setActive] = useState<string | null>(null); const [readyError, setReadyError] = useState<string | null>(null);
  useEffect(() => { void ensureReady().catch((error) => setReadyError(error instanceof Error ? error.message : String(error))); }, [ensureReady]);
  const fields = useMemo(() => document ? resolveSurface(document, editorSchema) : [], [document, editorSchema]);
  const activeField = fields.find((field) => field.id === active) ?? null;
  const findingFor = (field: ResolvedTuningField): string | null => validation?.findings.find((finding) => finding.severity === 'error' && (finding.documentPath === field.path || finding.location === field.path))?.message ?? null;
  const validate = async () => { if (!document) return; setLoading(true, 'Validating CINDER simulation case...'); try { setValidation(await validateSimulationCase(document)); } finally { setLoading(false); } };
  const reset = async () => { if (!window.confirm('Reset the editable tuning surface to the Baja launch baseline?')) return; setLoading(true, 'Loading Baja launch baseline...'); try { await loadPreset('baja-launch-baseline'); } finally { setLoading(false); } };
  const run = async () => { if (document) await runSimulation(document); };
  if (document === null) return <div className={styles.input}><LoadingOverlay isVisible={isLoading} message={loadingMessage} /><div className={styles.parameterInformationContainer}><ParameterDescription name="Loading Baja baseline" description={readyError ?? 'Loading the canonical CINDER simulation document…'} /></div></div>;
  return <div className={styles.input}><LoadingOverlay isVisible={isLoading} message={loadingMessage} />
    <div className={styles.topBar}><div className={styles.navButtons}><Button text="Home" icon={Home} onClick={() => navigate('/')} /><Button text="Baja Baseline" icon={ArrowLeft} onClick={() => void reset()} /></div><div className={styles.sessionInfo} title={source?.description ?? ''}><span className={styles.selectedSetName}>{source?.name ?? 'Baja Launch Baseline'}</span>{validation && <span className={styles.changesBadge}><span className={styles.changeIndicator} /><span>{validation.isValid ? 'Validated' : 'Needs attention'}</span></span>}</div><div className={styles.topBarSpacer} /></div>
    <div className={styles.inputGrid}><div className={styles.parameterInputContainer}>{GROUPS.map((group) => <ParameterAccordion key={group} title={GROUP_TITLES[group]} isExpanded={expanded[group]} onToggle={() => setExpanded((current) => ({ ...current, [group]: !current[group] }))}>{fields.filter((field) => field.group === group).map((field) => {
      const value = getValueAtJsonPointer(document, field.path); const error = findingFor(field); if (field.kind === 'ramp') { const editorValue = rampToEditor(value); return <div key={field.id} onFocus={() => setActive(field.id)}><RampBuilder value={editorValue} hasChanged={false} onChange={(next) => setValueAtPath(field.path, editorToRamp(next))} /></div>; }
      return typeof value === 'number' ? <DocumentQuantityInput key={field.id} label={field.label} valueSi={value} dimension={field.dimension} canonicalUnit={field.canonicalUnit} minimum={field.minimum} error={error} onFocus={() => setActive(field.id)} onChangeSi={(next) => setValueAtPath(field.path, next)} /> : null;
    })}</ParameterAccordion>)}</div>
      <div className={styles.parameterInformationContainer}><ParameterDescription name={activeField?.label ?? 'No Parameter Selected'} description={activeField?.description ?? 'Click on an input field to see its CINDER description.'} img={activeField?.image} />{activeField?.kind === 'ramp' && <RampPreview config={rampToEditor(getValueAtJsonPointer(document, activeField.path))} />}</div>
      <div className={styles.inputButtonsContainer}><Button text="Expand All" icon={ArrowDownCircle} onClick={() => setExpanded(expandedState)} /><Button text="Collapse All" icon={ArrowUpCircle} iconSide="right" onClick={() => setExpanded(collapsedState)} /></div>
      <div className={styles.nextButtonContainer}><Button text="Reset" icon={ArrowLeft} onClick={() => void reset()} /><Button text="Validate" icon={Edit} onClick={() => void validate()} /><Button text="Run" icon={PlayOutline} onClick={() => void run()} /></div>
    </div></div>;
};
