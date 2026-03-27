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

// Storage key for localStorage
const STORAGE_KEY = 'cvt-simulator-parameters';

// Load parameters from localStorage
const loadFromStorage = (): ParameterState => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      // Merge with defaults to ensure all parameters exist
      return { ...getInitialState(), ...parsed };
    }
  } catch (error) {
    alert(`Failed to load parameters from localStorage: ${error instanceof Error ? error.message : String(error)}`);
  }
  return getInitialState();
};

// Save parameters to localStorage
const saveToStorage = (parameters: ParameterState): void => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(parameters));
  } catch (error) {
    alert(`Failed to save parameters to localStorage: ${error instanceof Error ? error.message : String(error)}`);
  }
};

const parameterReducer = (state: ParameterState, action: ParameterAction): ParameterState => {
  let newState: ParameterState;
  
  switch (action.type) {
    case 'SET_PARAMETER':
      newState = { ...state, [action.parameter]: action.value };
      break;
    case 'SET_MULTIPLE_PARAMETERS':
      newState = { ...state, ...action.parameters };
      break;
    case 'RESET_TO_DEFAULTS':
      newState = getInitialState();
      break;
    default:
      return state;
  }
  
  saveToStorage(newState);
  
  return newState;
};

export const ParameterProvider = ({ children }: { children: React.ReactNode }) => {
  const [parameters, dispatch] = useReducer(parameterReducer, undefined, () => loadFromStorage());

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

// eslint-disable-next-line react-refresh/only-export-components
export const useParameter = () => {
  const context = useContext(ParameterContext);
  if (!context) throw new Error('useParameter must be used within ParameterProvider');
  return context;
};