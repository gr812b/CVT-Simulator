import React, { createContext, useState, useContext } from 'react';
import type { RunResponse } from '@utils/api';

interface SimulationContextType {
  simulationResult: RunResponse | null;
  setSimulationResult: (result: RunResponse | null) => void;
  isSimulationReady: boolean;
}

const SimulationContext = createContext<SimulationContextType | undefined>(undefined);

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

// eslint-disable-next-line react-refresh/only-export-components
export const useSimulation = (): SimulationContextType => {
  const context = useContext(SimulationContext);
  if (context === undefined) {
    throw new Error('useSimulation must be used within a SimulationProvider');
  }
  return context;
};