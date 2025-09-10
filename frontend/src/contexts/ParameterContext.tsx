import React, { createContext, useReducer, useContext } from 'react';

type ParameterAction = 
  | { type: 'SET_WEIGHT'; weight: number };

const ParameterContext = createContext<{
  weight: number;
  dispatch: React.Dispatch<ParameterAction>;
} | undefined>(undefined);

const parameterReducer = (state: { 
  title: string; sidebarOpen: boolean; layout: string; live: boolean; sources: string[]
}, action: ParameterAction) => {
  switch (action.type) {
    case 'SET_WEIGHT':
      return { ...state, weight: action.weight };
    default:
      return state;
  }
};

export const ParameterProvider = ({ children }: { children: React.ReactNode }) => {
  const initialState = {
    weight: 150, // TODO: Use default values in source of truth
  };

  const [state, dispatch] = useReducer(parameterReducer, initialState);

  return (
    <ParameterContext.Provider value={{ ...state, dispatch }}>
      {children}
    </ParameterContext.Provider>
  );
};

export const useParameter = () => {
  const context = useContext(ParameterContext);
  if (!context) throw new Error('useParameter must be used within ParameterProvider');
  return context;
};