import type { ParameterState } from '@types';

/**
 * Schema version for saved parameter sets
 * Increment this when making breaking changes to the parameter storage format
 */
const SCHEMA_VERSION = 1;

/**
 * Saved parameter set structure
 * Stores simulation configuration parameters (inputs), not simulation results
 */
export interface SavedSimulation {
  id: string;
  name: string;
  parameters: ParameterState;
  createdAt: string;
  updatedAt: string;
  schemaVersion: number;
}

/**
 * Storage configuration for different simulation types
 */
interface StorageConfig {
  key: string;
  idPrefix: string;
  maxItems?: number;
  sortBy: 'createdAt' | 'updatedAt';
}

/**
 * Storage configurations for different simulation types
 */
const STORAGE_CONFIGS = {
  saved: {
    key: 'cvt_saved_simulations',
    idPrefix: 'sim',
    sortBy: 'updatedAt' as const,
  },
  recent: {
    key: 'cvt_recent_runs',
    idPrefix: 'run',
    maxItems: 10,
    sortBy: 'createdAt' as const,
  },
} as const;

// ============================================================================
// Internal Helper Functions
// ============================================================================

/**
 * Generate a unique ID with the specified prefix
 */
const generateId = (prefix: string): string => {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
};

/**
 * Get simulations from localStorage with the given configuration
 */
const getSimulationsFromStorage = (config: StorageConfig): SavedSimulation[] => {
  try {
    const stored = localStorage.getItem(config.key);
    if (!stored) return [];
    
    const simulations: SavedSimulation[] = JSON.parse(stored);
    
    // Filter out simulations with incompatible schema versions
    const compatible = simulations.filter(sim => sim.schemaVersion === SCHEMA_VERSION);
    
    // If we filtered any out, update localStorage
    if (compatible.length !== simulations.length) {
      localStorage.setItem(config.key, JSON.stringify(compatible));
      console.warn(
        `Filtered out ${simulations.length - compatible.length} simulations with incompatible schema versions from ${config.key}`
      );
    }
    
    // Sort according to configuration (most recent first)
    return compatible.sort((a, b) => {
      const dateA = new Date(a[config.sortBy]).getTime();
      const dateB = new Date(b[config.sortBy]).getTime();
      return dateB - dateA;
    });
  } catch (error) {
    console.error(`Failed to load simulations from localStorage (${config.key}):`, error);
    return [];
  }
};

/**
 * Save simulations to localStorage with the given configuration
 */
const saveSimulationsToStorage = (
  simulations: SavedSimulation[], 
  config: StorageConfig
): void => {
  // Apply max items limit if configured
  const toSave = config.maxItems 
    ? simulations.slice(0, config.maxItems)
    : simulations;
  
  localStorage.setItem(config.key, JSON.stringify(toSave));
};

/**
 * Create a new SavedSimulation object
 */
const createSimulation = (
  id: string,
  name: string,
  parameters: ParameterState
): SavedSimulation => {
  const now = new Date().toISOString();
  return {
    id,
    name,
    parameters,
    createdAt: now,
    updatedAt: now,
    schemaVersion: SCHEMA_VERSION,
  };
};

/**
 * Core function to save a simulation to storage
 */
const saveToStorage = (
  config: StorageConfig,
  name: string,
  parameters: ParameterState,
  options?: { prepend?: boolean }
): SavedSimulation => {
  const simulations = getSimulationsFromStorage(config);
  const id = generateId(config.idPrefix);
  const newSimulation = createSimulation(id, name, parameters);
  
  // Add to beginning or end based on options
  const updated = options?.prepend 
    ? [newSimulation, ...simulations]
    : [...simulations, newSimulation];
  
  saveSimulationsToStorage(updated, config);
  
  return newSimulation;
};

// ============================================================================
// Public API - Saved Simulations
// ============================================================================

/**
 * Get all saved parameter sets from localStorage
 */
export const getAllSimulations = (): SavedSimulation[] => {
  return getSimulationsFromStorage(STORAGE_CONFIGS.saved);
};

/**
 * Get a single parameter set by ID
 */
export const getSimulation = (id: string): SavedSimulation | null => {
  const simulations = getAllSimulations();
  return simulations.find(sim => sim.id === id) || null;
};

/**
 * Save a new parameter set to localStorage
 */
export const saveSimulation = (name: string, parameters: ParameterState): SavedSimulation => {
  return saveToStorage(STORAGE_CONFIGS.saved, name, parameters);
};

/**
 * Update an existing parameter set
 */
export const updateSimulation = (
  id: string,
  updates: { name?: string; parameters?: ParameterState }
): SavedSimulation | null => {
  const simulations = getAllSimulations();
  const index = simulations.findIndex(sim => sim.id === id);
  
  if (index === -1) return null;
  
  const updated: SavedSimulation = {
    ...simulations[index],
    ...updates,
    updatedAt: new Date().toISOString(),
  };
  
  simulations[index] = updated;
  saveSimulationsToStorage(simulations, STORAGE_CONFIGS.saved);
  
  return updated;
};

/**
 * Delete a parameter set from localStorage
 */
export const deleteSimulation = (id: string): boolean => {
  const simulations = getAllSimulations();
  const filtered = simulations.filter(sim => sim.id !== id);
  
  if (filtered.length === simulations.length) return false;
  
  saveSimulationsToStorage(filtered, STORAGE_CONFIGS.saved);
  return true;
};

/**
 * Delete multiple parameter sets from localStorage
 */
export const deleteSimulations = (ids: string[]): number => {
  const simulations = getAllSimulations();
  const idSet = new Set(ids);
  const filtered = simulations.filter(sim => !idSet.has(sim.id));
  
  const deletedCount = simulations.length - filtered.length;
  
  if (deletedCount > 0) {
    saveSimulationsToStorage(filtered, STORAGE_CONFIGS.saved);
  }
  
  return deletedCount;
};

/**
 * Check if a parameter set name already exists
 */
export const simulationNameExists = (name: string, excludeId?: string): boolean => {
  const simulations = getAllSimulations();
  return simulations.some(sim => 
    sim.name.toLowerCase() === name.toLowerCase() && sim.id !== excludeId
  );
};

// ============================================================================
// Public API - Recent Runs
// ============================================================================

/**
 * Get all recent runs from localStorage
 */
export const getRecentRuns = (): SavedSimulation[] => {
  return getSimulationsFromStorage(STORAGE_CONFIGS.recent);
};

/**
 * Save a simulation run to recent runs history
 * Automatically maintains only the last 10 runs
 */
export const saveRecentRun = (parameters: ParameterState): SavedSimulation => {
  const timestamp = new Date();
  const name = `Run - ${timestamp.toLocaleString()}`;
  return saveToStorage(STORAGE_CONFIGS.recent, name, parameters, { prepend: true });
};

/**
 * Check if a simulation is a recent run
 */
export const isRecentRun = (id: string): boolean => {
  return id.startsWith(`${STORAGE_CONFIGS.recent.idPrefix}_`);
};

// ============================================================================
// Public API - Import/Export
// ============================================================================

/**
 * Export parameter set to JSON file
 */
export const exportSimulation = (simulation: SavedSimulation): void => {
  const dataStr = JSON.stringify(simulation, null, 2);
  const dataBlob = new Blob([dataStr], { type: 'application/json' });
  const url = URL.createObjectURL(dataBlob);
  
  const link = document.createElement('a');
  link.href = url;
  link.download = `${simulation.name.replace(/[^a-z0-9]/gi, '_')}.json`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  
  URL.revokeObjectURL(url);
};

/**
 * Import parameter set from JSON file
 */
export const importSimulation = async (file: File): Promise<SavedSimulation> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target?.result as string);
        
        // Validate the imported data
        if (!data.name || !data.parameters) {
          throw new Error('Invalid parameter file: missing required fields');
        }
        
        if (data.schemaVersion !== SCHEMA_VERSION) {
          throw new Error(
            `Incompatible schema version: expected ${SCHEMA_VERSION}, got ${data.schemaVersion}`
          );
        }
        
        // Create a new parameter set with imported data
        const imported = saveSimulation(data.name, data.parameters);
        resolve(imported);
      } catch (error) {
        reject(error);
      }
    };
    
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsText(file);
  });
};