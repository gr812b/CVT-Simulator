import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import styles from './Dashboard.module.scss';
import { Button } from '@components/button/Button';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { SimulationsTable } from '@components/simulationsTable/SimulationsTable';
import { useLoading } from '@contexts/LoadingContext';
import { useSimulationCase, type SimulationCaseSource } from '@contexts/SimulationCaseContext';
import { useRunSimulation } from '@hooks/useRunSimulation';
import { listPresets, loadPreset, type PresetSummary, type SimulationCaseDocument } from '@api/client';
import PlayOutline from '@assets/icons/play_outline.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import TrashCan from '@assets/icons/trash_can.svg?react';
import Plus from '@assets/icons/plus.svg?react';
import ArrowUpCircle from '@assets/icons/arrow_up_circle.svg?react';
import ArrowDownCircle from '@assets/icons/arrow_down_circle.svg?react';
import Home from '@assets/icons/home.svg?react';

const BASELINE_PRESET_ID = 'baja-launch-baseline';

function sourceFor(preset: PresetSummary): SimulationCaseSource {
  return { presetId: preset.id, name: preset.name, description: preset.description };
}

function downloadDocument(name: string, document: SimulationCaseDocument): void {
  const blob = new Blob([JSON.stringify(document, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = window.document.createElement('a');
  anchor.href = url;
  anchor.download = `${name.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase() || 'cinder-simulation-case'}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function readImportedDocument(raw: unknown): SimulationCaseDocument {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new Error('The selected file must contain a CINDER simulation document object.');
  }
  const candidate = raw as Record<string, unknown>;
  const document = candidate.simulation_case ?? candidate;
  if (typeof document !== 'object' || document === null || Array.isArray(document)) {
    throw new Error('The selected file does not contain a CINDER simulation document.');
  }
  return document as SimulationCaseDocument;
}

/**
 * Preserves the original simulation-library page while sourcing rows directly
 * from immutable CINDER presets. Imported documents remain browser-session
 * drafts; no legacy saved-parameter format is revived.
 */
export const Dashboard = () => {
  const navigate = useNavigate();
  const { isLoading, loadingMessage, setLoading } = useLoading();
  const { replaceDocument } = useSimulationCase();
  const { runSimulation } = useRunSimulation();
  const [presets, setPresets] = useState<PresetSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [isLoadingPresets, setIsLoadingPresets] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedPreset = useMemo(
    () => presets.find((preset) => preset.id === selectedId) ?? null,
    [presets, selectedId],
  );

  const refreshPresets = useCallback(async () => {
    setIsLoadingPresets(true);
    setListError(null);
    try {
      const next = await listPresets();
      setPresets(next);
      setSelectedId((current) => current && next.some((preset) => preset.id === current)
        ? current
        : (next.find((preset) => preset.id === BASELINE_PRESET_ID)?.id ?? next[0]?.id ?? null));
    } catch (error) {
      setListError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsLoadingPresets(false);
    }
  }, []);

  useEffect(() => { void refreshPresets(); }, [refreshPresets]);

  const resolveSelectedPreset = useCallback(async () => {
    if (selectedPreset === null) throw new Error('Select a CINDER preset first.');
    setLoading(true, `Loading ${selectedPreset.name}…`);
    const loaded = await loadPreset(selectedPreset.id);
    replaceDocument(loaded.simulationCase, sourceFor(loaded));
    return loaded;
  }, [replaceDocument, selectedPreset, setLoading]);

  const handleRun = useCallback(async () => {
    try {
      const loaded = await resolveSelectedPreset();
      await runSimulation(loaded.simulationCase);
    } catch (error) {
      alert(`Could not prepare simulation: ${error instanceof Error ? error.message : String(error)}`);
      setLoading(false);
    }
  }, [resolveSelectedPreset, runSimulation, setLoading]);

  const handleEdit = useCallback(async () => {
    try {
      await resolveSelectedPreset();
      navigate('/input');
    } catch (error) {
      alert(`Could not load simulation: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setLoading(false);
    }
  }, [navigate, resolveSelectedPreset, setLoading]);

  const handleExport = useCallback(async () => {
    try {
      const loaded = await resolveSelectedPreset();
      downloadDocument(loaded.name, loaded.simulationCase);
    } catch (error) {
      alert(`Could not export simulation: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setLoading(false);
    }
  }, [resolveSelectedPreset, setLoading]);

  const handleNew = useCallback(async () => {
    const baseline = presets.find((preset) => preset.id === BASELINE_PRESET_ID);
    if (!baseline) {
      alert('The Baja tuned-launch CINDER preset is not available from this backend.');
      return;
    }
    setSelectedId(baseline.id);
    try {
      setLoading(true, `Loading ${baseline.name}…`);
      const loaded = await loadPreset(baseline.id);
      replaceDocument(loaded.simulationCase, sourceFor(loaded));
      navigate('/input');
    } catch (error) {
      alert(`Could not create simulation: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setLoading(false);
    }
  }, [navigate, presets, replaceDocument, setLoading]);

  const handleImport = useCallback(() => fileInputRef.current?.click(), []);
  const handleFileChange = useCallback(async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    try {
      setLoading(true, `Importing ${file.name}…`);
      const imported = readImportedDocument(JSON.parse(await file.text()));
      replaceDocument(imported, {
        presetId: `local:${file.name}`,
        name: file.name.replace(/\.json$/i, ''),
        description: 'Imported CINDER simulation document (browser-session draft).',
      });
      navigate('/input');
    } catch (error) {
      alert(`Could not import simulation: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setLoading(false);
    }
  }, [navigate, replaceDocument, setLoading]);

  return (
    <div className={styles.dashboard}>
      <LoadingOverlay isVisible={isLoading} message={loadingMessage} />
      <div className={styles.topBar}>
        <Button text="Home" icon={Home} className={styles.navButton} onClick={() => navigate('/')} />
      </div>
      <SimulationsTable
        presets={presets}
        selectedId={selectedId}
        onSelect={setSelectedId}
        isLoading={isLoadingPresets}
        error={listError}
      />
      <div className={styles.buttonsContainer}>
        <Button text="Run" icon={PlayOutline} className={styles.button} disabled={selectedPreset === null} onClick={() => void handleRun()} />
        <Button text="Edit" icon={Edit} className={styles.button} disabled={selectedPreset === null} onClick={() => void handleEdit()} />
        <Button text="Delete" icon={TrashCan} className={styles.button} disabled title="CINDER backend presets are immutable." />
        <Button text="Export" icon={ArrowUpCircle} className={styles.button} disabled={selectedPreset === null} onClick={() => void handleExport()} />
        <Button text="Import" icon={ArrowDownCircle} className={styles.button} onClick={handleImport} />
        <Button text="New" icon={Plus} className={styles.button} onClick={() => void handleNew()} />
      </div>
      <input ref={fileInputRef} type="file" accept="application/json,.json" style={{ display: 'none' }} onChange={handleFileChange} />
    </div>
  );
};
