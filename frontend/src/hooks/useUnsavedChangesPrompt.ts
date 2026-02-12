import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

export const useUnsavedChangesPrompt = (hasChanges: boolean) => {
  const navigate = useNavigate();

  // Session persistence handles auto-save, so no need for beforeunload warning
  // Keeping this hook for potential future use of navigateWithConfirmation

  // Create a function to navigate (no confirmation needed with session persistence)
  const navigateWithConfirmation = useCallback((to: string) => {
    navigate(to);
  }, [navigate]);

  return { navigateWithConfirmation };
};