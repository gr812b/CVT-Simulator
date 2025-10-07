import React, { createContext, useState } from 'react';
import type { RunResponse } from '@utils/api';

export interface SimulationContextType {
  simulationResult: RunResponse | null;
  setSimulationResult: (result: RunResponse | null) => void;
  isSimulationReady: boolean;
}

export const SimulationContext = createContext<SimulationContextType | undefined>(undefined);

export const SimulationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [simulationResult, setSimulationResult] = useState<RunResponse | null>(null);

  const isSimulationReady = simulationResult !== null;

  return (
    <SimulationContext.Provider value={{ 
      simulationResult, 
      setSimulationResult, 
      isSimulationReady 
    }}>
      {children}
    </SimulationContext.Provider>
  );
};