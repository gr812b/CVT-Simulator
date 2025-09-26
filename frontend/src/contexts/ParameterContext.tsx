import React, { createContext, useReducer, useContext } from 'react';
import { PARAMETERS, type Parameter, type ParameterState } from '@types';

type ParameterAction = 
  | { type: 'SET_PARAMETER'; parameter: Parameter; value: ParameterState[Parameter] }
  | { type: 'SET_MULTIPLE_PARAMETERS'; parameters: Partial<ParameterState> }
  | { type: 'RESET_TO_DEFAULTS' };

const ParameterContext = createContext<{
  parameters: ParameterState;
  dispatch: React.Dispatch<ParameterAction>;
  setParameter: (parameter: Parameter, value: ParameterState[Parameter]) => void;
  setMultipleParameters: (parameters: Partial<ParameterState>) => void;
  resetToDefaults: () => void;
} | undefined>(undefined);

// Create initial state from PARAMETERS defaults
const getInitialState = (): ParameterState => {
  const result = {} as Record<Parameter, unknown>;
  
  for (const [key, config] of Object.entries(PARAMETERS)) {
    result[key as Parameter] = config.defaultValue;
  }
  
  return result as ParameterState;
};

const parameterReducer = (state: ParameterState, action: ParameterAction): ParameterState => {
  switch (action.type) {
    case 'SET_PARAMETER':
      return { ...state, [action.parameter]: action.value };
    case 'SET_MULTIPLE_PARAMETERS':
      return { ...state, ...action.parameters };
    case 'RESET_TO_DEFAULTS':
      return getInitialState();
    default:
      return state;
  }
};

export const ParameterProvider = ({ children }: { children: React.ReactNode }) => {
  const [parameters, dispatch] = useReducer(parameterReducer, getInitialState());

  const setParameter = (parameter: Parameter, value: ParameterState[Parameter]) => {
    dispatch({ type: 'SET_PARAMETER', parameter, value });
  };

  const setMultipleParameters = (params: Partial<ParameterState>) => {
    dispatch({ type: 'SET_MULTIPLE_PARAMETERS', parameters: params });
  };

  const resetToDefaults = () => {
    dispatch({ type: 'RESET_TO_DEFAULTS' });
  };

  return (
    <ParameterContext.Provider value={{ 
      parameters, 
      dispatch,
      setParameter,
      setMultipleParameters,
      resetToDefaults 
    }}>
      {children}
    </ParameterContext.Provider>
  );
};

export const useParameter = () => {
  const context = useContext(ParameterContext);
  if (!context) throw new Error('useParameter must be used within ParameterProvider');
  return context;
};