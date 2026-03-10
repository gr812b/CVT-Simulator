import { useEffect, useCallback, useMemo } from 'react';
import { useParameter } from '@contexts/ParameterContext';
import type { ParameterState } from '@types';
import {
  saveSessionParameters,
  getSessionParameters,
  clearSessionParameters,
  setLoadedSimulationId,
  getLoadedSimulationId,
  getSimulation,
} from '@utils/localStorage';
import { getDefaultSimulations } from '@constants/defaultSimulations';

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

  /**
   * Initialize: Load session parameters or check for loaded simulation
   */
  useEffect(() => {
    const sessionParams = getSessionParameters();
    const loadedId = getLoadedSimulationId();
    
    if (sessionParams && loadedId) {
      // Both exist - restore session and keep baseline reference
      setMultipleParameters(sessionParams);
    } else if (sessionParams && !loadedId) {
      // Session exists but no baseline - this is a page reload
      // Set the session state and mark it as the baseline by storing it with a special ID
      setMultipleParameters(sessionParams);
      setLoadedSimulationId('session_baseline');
    } else if (!sessionParams && !loadedId) {
      // Fresh start - load first default and set it as baseline
      const defaults = getDefaultSimulations();
      if (defaults[0]) {
        setMultipleParameters(defaults[0].parameters);
        setLoadedSimulationId(defaults[0].id);
      }
    }
    // else: loadedId exists without session (from dashboard), parameters already set
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run on mount

  /**
   * Auto-save parameters to session on change
   */
  useEffect(() => {
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
    
    // Fallback
    return parameters;
  }, [parameters]); // Note: loadedId is read inside, but changes are rare

  /**
   * Check if current parameters differ from baseline
   */
  const hasChanges = useCallback((): boolean => {
    return JSON.stringify(parameters) !== JSON.stringify(baselineParameters);
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
      const changed = currentStr !== baselineStr;
      
      // Only log if actually changed (reduces noise)
      if (changed) {
        console.log(`[Field Check] ${String(field)}: CHANGED`, {
          loadedId,
          current: parameters[field],
          baseline: baselineParameters[field]
        });
      }
      
      return changed;
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
