import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

interface LoadingContextType {
  isLoading: boolean;
  loadingMessage: string;
  setLoading: (loading: boolean, message?: string) => void;
}

const LoadingContext = createContext<LoadingContextType | undefined>(undefined);

export const LoadingProvider = ({ children }: { children: React.ReactNode }) => {
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('Loading...');

  const setLoading = useCallback((loading: boolean, message = 'Loading...') => {
    setIsLoading(loading);
    setLoadingMessage(message);
  }, []);

  const value = useMemo<LoadingContextType>(() => ({
    isLoading,
    loadingMessage,
    setLoading,
  }), [isLoading, loadingMessage, setLoading]);

  return (
    <LoadingContext.Provider value={value}>
      {children}
    </LoadingContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useLoading = (): LoadingContextType => {
  const context = useContext(LoadingContext);
  if (context === undefined) {
    throw new Error('useLoading must be used within LoadingProvider');
  }
  return context;
};
