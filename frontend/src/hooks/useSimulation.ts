import { useContext } from 'react';
import { SimulationContext, type SimulationContextType } from '@contexts/SimulationContext';

export const useSimulation = (): SimulationContextType => {
  const context = useContext(SimulationContext);
  if (context === undefined) {
    throw new Error('useSimulation must be used within a SimulationProvider');
  }
  return context;
};