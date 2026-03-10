import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useParameter } from '@contexts/ParameterContext';
import { useRunSimulation } from '@hooks/useRunSimulation';
import {
  getAllSimulations,
  deleteSimulation,
  exportSimulation,
  importSimulation,
  getRecentRuns,
  isRecentRun,
  setLoadedSimulationId,
  clearSessionParameters,
  type SavedSimulation,
} from '@utils/localStorage';
import { getDefaultSimulations, isDefaultSimulation } from '@constants/defaultSimulations';

export interface GroupedSimulations {
  defaults: SavedSimulation[];
  saved: SavedSimulation[];
  recentRuns: SavedSimulation[];
}

export interface UseSimulationsReturn {
  simulations: SavedSimulation[];
  groupedSimulations: GroupedSimulations;
  selectedSimulation: SavedSimulation | null;
  selectedId: string | null;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  // Selection state
  hasSelection: boolean;
  isDefaultSelected: boolean;
  isRecentRunSelected: boolean;
  canDelete: boolean;
  // Actions
  selectSimulation: (id: string) => void;
  handleRun: () => Promise<void>;
  handleEdit: () => void;
  handleDelete: () => void;
  handleExport: () => void;
  handleImport: () => void;
  handleNew: () => void;
  handleFileChange: (event: React.ChangeEvent<HTMLInputElement>) => Promise<void>;
  refresh: () => void;
}

/**
 * Custom hook for managing simulations
 * Encapsulates all simulation CRUD operations, selection state, and import/export
 */
export const useSimulations = (): UseSimulationsReturn => {
  const navigate = useNavigate();
  const { setMultipleParameters } = useParameter();
  const { runSimulation } = useRunSimulation();
  const [simulations, setSimulations] = useState<SavedSimulation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadSimulations = useCallback(() => {
    const userSimulations = getAllSimulations();
    const defaultSimulations = getDefaultSimulations();
    const recentRuns = getRecentRuns();
    const allSimulations = [...defaultSimulations, ...userSimulations, ...recentRuns];
    setSimulations(allSimulations);

    // Clear selection if the selected simulation no longer exists
    setSelectedId((prev) => {
      if (prev && !allSimulations.find((s) => s.id === prev)) {
        return null;
      }
      return prev;
    });
  }, []);

  useEffect(() => {
    loadSimulations();
  }, [loadSimulations]);

  // Derived state
  const selectedSimulation = selectedId
    ? simulations.find((s) => s.id === selectedId) ?? null
    : null;

  const hasSelection = !!selectedId;
  const isDefaultSelected = selectedId ? isDefaultSimulation(selectedId) : false;
  const isRecentRunSelected = selectedId ? isRecentRun(selectedId) : false;
  const canDelete = hasSelection && !isDefaultSelected && !isRecentRunSelected;

  const groupedSimulations: GroupedSimulations = {
    defaults: simulations.filter((s) => isDefaultSimulation(s.id)),
    saved: simulations.filter((s) => !isDefaultSimulation(s.id) && !isRecentRun(s.id)),
    recentRuns: simulations.filter((s) => isRecentRun(s.id)),
  };

  // Actions
  const selectSimulation = useCallback((id: string) => {
    setSelectedId((prev) => (id === prev ? null : id));
  }, []);

  const handleRun = useCallback(async () => {
    if (!selectedSimulation) return;
    await runSimulation(selectedSimulation.parameters);
  }, [selectedSimulation, runSimulation]);

  const handleEdit = useCallback(() => {
    if (!selectedSimulation) return;

    setMultipleParameters(selectedSimulation.parameters);
    setLoadedSimulationId(selectedId);
    navigate('/input');
  }, [selectedSimulation, selectedId, setMultipleParameters, navigate]);

  const handleDelete = useCallback(() => {
    if (!selectedSimulation || !selectedId) return;

    if (isDefaultSimulation(selectedId)) {
      alert('Default parameter sets cannot be deleted.');
      return;
    }

    if (isRecentRun(selectedId)) {
      alert('Recent runs cannot be deleted. They will automatically be removed as new runs are added.');
      return;
    }

    if (confirm(`Are you sure you want to delete the parameter set "${selectedSimulation.name}"?`)) {
      deleteSimulation(selectedId);
      loadSimulations();
    }
  }, [selectedSimulation, selectedId, loadSimulations]);

  const handleExport = useCallback(() => {
    if (!selectedSimulation) return;
    exportSimulation(selectedSimulation);
  }, [selectedSimulation]);

  const handleImport = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleNew = useCallback(() => {
    clearSessionParameters();
    setLoadedSimulationId(null);
    navigate('/input');
  }, [navigate]);

  const handleFileChange = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      try {
        await importSimulation(file);
        loadSimulations();
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
      } catch (error) {
        console.error('Import failed:', error);
        alert('Failed to import parameter set. Please check the file format.');
      }
    },
    [loadSimulations]
  );

  return {
    simulations,
    groupedSimulations,
    selectedSimulation,
    selectedId,
    fileInputRef,
    hasSelection,
    isDefaultSelected,
    isRecentRunSelected,
    canDelete,
    selectSimulation,
    handleRun,
    handleEdit,
    handleDelete,
    handleExport,
    handleImport,
    handleNew,
    handleFileChange,
    refresh: loadSimulations,
  };
};
