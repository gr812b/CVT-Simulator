import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import {
  loadPreset as fetchPreset,
  type SimulationCaseDocument,
  type SimulationCaseValidation,
} from '@api/client';
import { setValueAtJsonPointer, type JsonValue } from '@utils/jsonPointer';

const DOCUMENT_STORAGE_KEY = 'cinder-simulation-case-v1';
const SOURCE_STORAGE_KEY = 'cinder-simulation-case-source-v1';

export interface SimulationCaseSource {
  presetId: string;
  name: string;
  description: string;
}

interface SimulationCaseContextValue {
  document: SimulationCaseDocument | null;
  source: SimulationCaseSource | null;
  validation: SimulationCaseValidation | null;
  replaceDocument: (document: SimulationCaseDocument, source?: SimulationCaseSource | null) => void;
  setValueAtPath: (path: string, value: JsonValue) => void;
  loadPreset: (presetId: string) => Promise<SimulationCaseSource>;
  setValidation: (validation: SimulationCaseValidation | null) => void;
  clearDocument: () => void;
}

const SimulationCaseContext = createContext<SimulationCaseContextValue | undefined>(undefined);

function readStored<T>(key: string): T | null {
  try {
    const value = localStorage.getItem(key);
    return value === null ? null : (JSON.parse(value) as T);
  } catch {
    localStorage.removeItem(key);
    return null;
  }
}

function persist(document: SimulationCaseDocument | null, source: SimulationCaseSource | null): void {
  if (document === null) localStorage.removeItem(DOCUMENT_STORAGE_KEY);
  else localStorage.setItem(DOCUMENT_STORAGE_KEY, JSON.stringify(document));
  if (source === null) localStorage.removeItem(SOURCE_STORAGE_KEY);
  else localStorage.setItem(SOURCE_STORAGE_KEY, JSON.stringify(source));
}

/** One canonical, raw CINDER document; not a parallel parameter state. */
export const SimulationCaseProvider = ({ children }: { children: ReactNode }) => {
  const [document, setDocument] = useState<SimulationCaseDocument | null>(() => readStored(DOCUMENT_STORAGE_KEY));
  const [source, setSource] = useState<SimulationCaseSource | null>(() => readStored(SOURCE_STORAGE_KEY));
  const [validation, setValidation] = useState<SimulationCaseValidation | null>(null);

  const replaceDocument = useCallback((next: SimulationCaseDocument, nextSource: SimulationCaseSource | null = null) => {
    setDocument(next);
    setSource(nextSource);
    setValidation(null);
    persist(next, nextSource);
  }, []);

  const setValueAtPath = useCallback((path: string, value: JsonValue) => {
    setDocument((current) => {
      if (current === null) throw new Error('Load a CINDER document before editing it.');
      const next = setValueAtJsonPointer(current, path, value);
      persist(next, source);
      return next;
    });
    setValidation(null);
  }, [source]);

  const loadPreset = useCallback(async (presetId: string): Promise<SimulationCaseSource> => {
    const preset = await fetchPreset(presetId);
    const nextSource = { presetId: preset.id, name: preset.name, description: preset.description };
    replaceDocument(preset.simulationCase, nextSource);
    return nextSource;
  }, [replaceDocument]);

  const clearDocument = useCallback(() => {
    setDocument(null);
    setSource(null);
    setValidation(null);
    persist(null, null);
  }, []);

  const value = useMemo(() => ({
    document,
    source,
    validation,
    replaceDocument,
    setValueAtPath,
    loadPreset,
    setValidation,
    clearDocument,
  }), [clearDocument, document, loadPreset, replaceDocument, setValueAtPath, source, validation]);

  return <SimulationCaseContext.Provider value={value}>{children}</SimulationCaseContext.Provider>;
};

export function useSimulationCase(): SimulationCaseContextValue {
  const value = useContext(SimulationCaseContext);
  if (value === undefined) throw new Error('useSimulationCase must be used inside SimulationCaseProvider.');
  return value;
}
