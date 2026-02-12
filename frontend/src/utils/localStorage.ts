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
 * Local storage key for saved parameter sets
 */
const STORAGE_KEY = 'cvt_saved_simulations';

/**
 * Local storage key for recent runs
 */
const RECENT_RUNS_KEY = 'cvt_recent_runs';
const MAX_RECENT_RUNS = 10;

/**
 * Generate a unique ID for a parameter set
 */
const generateId = (): string => {
  return `sim_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
};

/**
 * Get all saved parameter sets from localStorage
 */
export const getAllSimulations = (): SavedSimulation[] => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return [];
    
    const simulations: SavedSimulation[] = JSON.parse(stored);
    
    // Filter out parameter sets with incompatible schema versions
    const compatible = simulations.filter(sim => sim.schemaVersion === SCHEMA_VERSION);
    
    // If we filtered any out, update localStorage
    if (compatible.length !== simulations.length) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(compatible));
      console.warn(`Filtered out ${simulations.length - compatible.length} parameter sets with incompatible schema versions`);
    }
    
    return compatible.sort((a, b) => 
      new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
    );
  } catch (error) {
    console.error('Failed to load simulations from localStorage:', error);
    return [];
  }
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
  const simulations = getAllSimulations();
  
  const newSimulation: SavedSimulation = {
    id: generateId(),
    name,
    parameters,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    schemaVersion: SCHEMA_VERSION,
  };
  
  simulations.push(newSimulation);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(simulations));
  
  return newSimulation;
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
  localStorage.setItem(STORAGE_KEY, JSON.stringify(simulations));
  
  return updated;
};

/**
 * Delete a parameter set from localStorage
 */
export const deleteSimulation = (id: string): boolean => {
  const simulations = getAllSimulations();
  const filtered = simulations.filter(sim => sim.id !== id);
  
  if (filtered.length === simulations.length) return false;
  
  localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
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
    localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
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
/**
 * Get all recent runs from localStorage
 */
export const getRecentRuns = (): SavedSimulation[] => {
  try {
    const stored = localStorage.getItem(RECENT_RUNS_KEY);
    if (!stored) return [];
    
    const runs: SavedSimulation[] = JSON.parse(stored);
    
    // Sort by most recent first
    return runs.sort((a, b) => 
      new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    );
  } catch (error) {
    console.error('Failed to load recent runs from localStorage:', error);
    return [];
  }
};

/**
 * Save a simulation run to recent runs history
 * Automatically maintains only the last 10 runs
 */
export const saveRecentRun = (parameters: ParameterState): SavedSimulation => {
  const runs = getRecentRuns();
  
  const timestamp = new Date();
  const newRun: SavedSimulation = {
    id: `run_${timestamp.getTime()}`,
    name: `Run - ${timestamp.toLocaleString()}`,
    parameters,
    createdAt: timestamp.toISOString(),
    updatedAt: timestamp.toISOString(),
    schemaVersion: SCHEMA_VERSION,
  };
  
  // Add to beginning and keep only last 10
  const updatedRuns = [newRun, ...runs].slice(0, MAX_RECENT_RUNS);
  localStorage.setItem(RECENT_RUNS_KEY, JSON.stringify(updatedRuns));
  
  return newRun;
};

/**
 * Check if a simulation is a recent run
 */
export const isRecentRun = (id: string): boolean => {
  return id.startsWith('run_');
};
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
        if (!data.name || !data.parameters || data.schemaVersion !== SCHEMA_VERSION) {
          throw new Error('Invalid parameter file or incompatible schema version');
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
