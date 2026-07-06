import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import {
  getEditorSchema,
  loadPreset as requestPreset,
  type EditorSchema,
  type SimulationCaseDocument,
  type SimulationCaseValidation,
} from '@api/client';
import { setValueAtJsonPointer, type JsonValue } from '@utils/jsonPointer';

const DOCUMENT_STORAGE_KEY = 'cinder-simulation-case-v2';
const SOURCE_STORAGE_KEY = 'cinder-simulation-case-source-v2';

export interface SimulationCaseSource {
  presetId: string;
  name: string;
  description: string;
}

interface SimulationCaseContextValue {
  document: SimulationCaseDocument | null;
  source: SimulationCaseSource | null;
  editorSchema: EditorSchema | null;
  validation: SimulationCaseValidation | null;
  isLoadingDocument: boolean;
  loadError: string | null;
  ensureReady: () => Promise<void>;
  loadPreset: (presetId: string) => Promise<void>;
  replaceDocument: (document: SimulationCaseDocument, source?: SimulationCaseSource | null) => void;
  setValueAtPath: (path: string, value: JsonValue) => void;
  setValidation: (validation: SimulationCaseValidation | null) => void;
}

const SimulationCaseContext = createContext<SimulationCaseContextValue | undefined>(undefined);

function readStored<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? null : JSON.parse(raw) as T;
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

/** The frontend owns one raw CINDER document, never a second parameter map. */
export const SimulationCaseProvider = ({ children }: { children: ReactNode }) => {
  const [document, setDocument] = useState<SimulationCaseDocument | null>(() => readStored(DOCUMENT_STORAGE_KEY));
  const [source, setSource] = useState<SimulationCaseSource | null>(() => readStored(SOURCE_STORAGE_KEY));
  const [editorSchema, setEditorSchema] = useState<EditorSchema | null>(null);
  const [validation, setValidation] = useState<SimulationCaseValidation | null>(null);
  const [isLoadingDocument, setIsLoadingDocument] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const replaceDocument = useCallback((next: SimulationCaseDocument, nextSource: SimulationCaseSource | null = null) => {
    setDocument(next);
    setSource(nextSource);
    setValidation(null);
    persist(next, nextSource);
  }, []);

  const loadPreset = useCallback(async (presetId: string) => {
    setIsLoadingDocument(true);
    setLoadError(null);
    try {
      const preset = await requestPreset(presetId);
      replaceDocument(preset.simulationCase, {
        presetId: preset.id,
        name: preset.name,
        description: preset.description,
      });
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : String(error));
      throw error;
    } finally {
      setIsLoadingDocument(false);
    }
  }, [replaceDocument]);

  const ensureReady = useCallback(async () => {
    setIsLoadingDocument(true);
    setLoadError(null);
    try {
      const schemaPromise = editorSchema === null ? getEditorSchema() : Promise.resolve(editorSchema);
      const documentPromise = document === null ? requestPreset('baja-launch-baseline') : Promise.resolve(null);
      const [schema, preset] = await Promise.all([schemaPromise, documentPromise]);
      if (editorSchema === null) setEditorSchema(schema);
      if (preset !== null) {
        replaceDocument(preset.simulationCase, {
          presetId: preset.id,
          name: preset.name,
          description: preset.description,
        });
      }
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : String(error));
      throw error;
    } finally {
      setIsLoadingDocument(false);
    }
  }, [document, editorSchema, replaceDocument]);

  const setValueAtPath = useCallback((path: string, value: JsonValue) => {
    setDocument((current) => {
      if (current === null) throw new Error('No CINDER simulation document is loaded.');
      const next = setValueAtJsonPointer(current, path, value);
      persist(next, source);
      return next;
    });
    setValidation(null);
  }, [source]);

  const contextValue = useMemo<SimulationCaseContextValue>(() => ({
    document,
    source,
    editorSchema,
    validation,
    isLoadingDocument,
    loadError,
    ensureReady,
    loadPreset,
    replaceDocument,
    setValueAtPath,
    setValidation,
  }), [document, source, editorSchema, validation, isLoadingDocument, loadError, ensureReady, loadPreset, replaceDocument, setValueAtPath]);

  return <SimulationCaseContext.Provider value={contextValue}>{children}</SimulationCaseContext.Provider>;
};

// eslint-disable-next-line react-refresh/only-export-components
export function useSimulationCase(): SimulationCaseContextValue {
  const context = useContext(SimulationCaseContext);
  if (context === undefined) throw new Error('useSimulationCase must be used inside SimulationCaseProvider.');
  return context;
}
