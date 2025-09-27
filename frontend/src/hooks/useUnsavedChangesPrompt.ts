import { useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

export const useUnsavedChangesPrompt = (hasChanges: boolean) => {
  const navigate = useNavigate();

  // Handle browser back/refresh
  useEffect(() => {
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (hasChanges) {
        event.preventDefault();
        event.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
        return event.returnValue;
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [hasChanges]);

  // Create a function to navigate with confirmation
  const navigateWithConfirmation = useCallback((to: string) => {
    if (hasChanges) {
      const confirmed = window.confirm('You have unsaved changes. Are you sure you want to leave without saving?');
      if (confirmed) {
        navigate(to);
      }
    } else {
      navigate(to);
    }
  }, [hasChanges, navigate]);

  return { navigateWithConfirmation };
};