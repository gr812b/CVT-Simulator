import { useEffect, useCallback, useMemo, useLayoutEffect, useRef } from 'react';
import { useParameter } from '@contexts/ParameterContext';
import type { ParameterState } from '@types';
import {
  saveSessionParameters,
  getSessionParameters,
  clearSessionParameters,
  setLoadedSimulationId,
  getLoadedSimulationId,
  getSimulation,
  getRecentRuns,
} from '@utils/localStorage';
import { getDefaultSimulations } from '@constants/defaultSimulations';
import { PARAMETERS, type Parameter } from '@types';

/**
 * Hook for managing session persistence and tracking parameter changes
 * 
 * Features:
 * - Auto-saves parameters to sessionStorage on change
 * - Loads session parameters on mount if available
 * - Tracks which simulation was loaded for comparison
 * - Provides utilities to check if parameters have changed
 */
export const useSessionPersistence = () => {
  const { parameters, setMultipleParameters } = useParameter();
  const isHydratedRef = useRef(false);
  const hasSkippedInitialSaveRef = useRef(false);

  /**
   * Initialize: Load session parameters or check for loaded simulation
   */
  useLayoutEffect(() => {
    const sessionParams = getSessionParameters();
    const loadedId = getLoadedSimulationId();
    const defaults = getDefaultSimulations();
    
    if (sessionParams) {
      // Session always has highest priority on reload/navigation
      setMultipleParameters(sessionParams);
      if (!loadedId) {
        // Keep a baseline marker so changed detection has a stable reference
        setLoadedSimulationId('session_baseline');
      }
    } else if (loadedId) {
      // No session state available; restore from the selected simulation ID
      const savedSimulation = getSimulation(loadedId);
      if (savedSimulation) {
        setMultipleParameters(savedSimulation.parameters);
      } else {
        const recentRun = getRecentRuns().find(sim => sim.id === loadedId);
        if (recentRun) {
          setMultipleParameters(recentRun.parameters);
        } else {
        const defaultSimulation = defaults.find(sim => sim.id === loadedId);
        if (defaultSimulation) {
          setMultipleParameters(defaultSimulation.parameters);
        } else if (defaults[0]) {
          // Loaded ID is stale; fall back to first default
          setMultipleParameters(defaults[0].parameters);
          setLoadedSimulationId(defaults[0].id);
        } else {
          setLoadedSimulationId(null);
        }
        }
      }
    } else if (defaults[0]) {
      // Fresh start fallback
      setMultipleParameters(defaults[0].parameters);
      setLoadedSimulationId(defaults[0].id);
    }

    isHydratedRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * Auto-save parameters to session on change
   */
  useEffect(() => {
    if (!isHydratedRef.current) return;
    if (!hasSkippedInitialSaveRef.current) {
      hasSkippedInitialSaveRef.current = true;
      return;
    }
    saveSessionParameters(parameters);
  }, [parameters]);

  /**
   * Get the baseline parameters for comparison (cached)
   * Only recomputes when loadedId changes
   */
  const baselineParameters = useMemo((): ParameterState => {
    const loadedId = getLoadedSimulationId();
    
    if (!loadedId) {
      // No baseline set - shouldn't happen, but use defaults
      const defaults = getDefaultSimulations();
      return defaults[0]?.parameters || parameters;
    }
    
    // Special case: session baseline (after reload)
    if (loadedId === 'session_baseline') {
      // Get the session parameters that were saved
      const sessionParams = getSessionParameters();
      return sessionParams || parameters;
    }
    
    // Check if it's a saved simulation
    const simulation = getSimulation(loadedId);
    if (simulation) {
      return simulation.parameters;
    }
    
    // Check if it's a default simulation
    const defaults = getDefaultSimulations();
    const defaultSim = defaults.find(s => s.id === loadedId);
    if (defaultSim) {
      return defaultSim.parameters;
    }

    // Check if it's a recent run
    const recentRun = getRecentRuns().find(s => s.id === loadedId);
    if (recentRun) {
      return recentRun.parameters;
    }
    
    // Fallback
    return parameters;
  }, [parameters]); // Note: loadedId is read inside, but changes are rare

  /**
   * Check if current parameters differ from baseline
   */
  const hasChanges = useCallback((): boolean => {
    return (Object.keys(PARAMETERS) as Parameter[]).some((field) => {
      const currentStr = JSON.stringify(parameters[field]);
      const baselineStr = JSON.stringify(baselineParameters[field]);
      return currentStr !== baselineStr;
    });
  }, [parameters, baselineParameters]);

  /**
   * Check if a specific parameter has changed from baseline
   */
  const isFieldChanged = useCallback(
    <K extends keyof ParameterState>(field: K): boolean => {
      const loadedId = getLoadedSimulationId();
      
      // If no loaded ID, nothing can be changed (shouldn't happen with our init logic)
      if (!loadedId) {
        return false;
      }
      
      const currentStr = JSON.stringify(parameters[field]);
      const baselineStr = JSON.stringify(baselineParameters[field]);
      return currentStr !== baselineStr;
    },
    [parameters, baselineParameters]
  );

  /**
   * Set which simulation is currently loaded (for comparison)
   */
  const setLoadedSimulation = useCallback((id: string | null) => {
    setLoadedSimulationId(id);
  }, []);

  /**
   * Clear session and reset to defaults
   */
  const clearSession = useCallback(() => {
    clearSessionParameters();
    setLoadedSimulationId(null);
  }, []);

  /**
   * Reset to baseline parameters
   */
  const resetToBaseline = useCallback(() => {
    setMultipleParameters(baselineParameters);
  }, [baselineParameters, setMultipleParameters]);

  return {
    hasChanges,
    isFieldChanged,
    setLoadedSimulation,
    clearSession,
    resetToBaseline,
    baselineParameters, // Export for direct access
  };
};
