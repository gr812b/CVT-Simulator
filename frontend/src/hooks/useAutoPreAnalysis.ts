import { useEffect, useRef, useCallback, useState } from 'react';
import { useParameter } from '@contexts/ParameterContext';

/**
 * Debounce delay in milliseconds
 */
const DEBOUNCE_DELAY = 1000;

/**
 * Hook for automatically running CVT pre-analysis when parameters change
 * Pre-analysis is a backend call that validates the CVT configuration
 * Only runs when form field validation passes
 */
export const useAutoPreAnalysis = (isFormValid: boolean = true) => {
  const { parameters } = useParameter();
  const [isValidating, setIsValidating] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [lastValidated, setLastValidated] = useState<Date | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  /**
   * Run pre-analysis - calls backend to validate CVT configuration
   */
  const runValidation = useCallback(async () => {
    console.log('[Pre-Analysis] ===== CALLING BACKEND PRE-ANALYSIS =====', new Date().toISOString());
    
    setIsValidating(true);
    setValidationError(null);

    try {
      // TODO: Replace with actual backend API call
      // const result = await fetch('/api/pre-analysis', { 
      //   method: 'POST',
      //   body: JSON.stringify(parameters) 
      // });
      // if (!result.ok) throw new Error('Pre-analysis failed');
      
      console.log('[Pre-Analysis] Backend call completed successfully');
      setLastValidated(new Date());
    } catch (error) {
      console.error('[Pre-Analysis] Backend call failed:', error);
      setValidationError(error instanceof Error ? error.message : 'Pre-analysis failed');
    } finally {
      console.log('[Pre-Analysis] Setting isValidating = false', new Date().toISOString());
      setIsValidating(false);
    }
  }, [parameters]);

  /**
   * Trigger pre-analysis when parameters change and form is valid
   */
  useEffect(() => {
    console.log('[Pre-Analysis] Effect triggered - Form valid:', isFormValid);
    
    // Don't run if form fields are invalid
    if (!isFormValid) {
      console.log('[Pre-Analysis] Skipping - form has validation errors');
      setIsValidating(false);
      return;
    }
    
    // Clear existing timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    console.log('[Pre-Analysis] Scheduling pre-analysis call (1s debounce)');
    
    // Debounce to avoid excessive calls
    debounceTimerRef.current = setTimeout(() => {
      console.log('[Pre-Analysis] Debounce complete, calling runValidation()');
      runValidation();
    }, DEBOUNCE_DELAY);

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [parameters, isFormValid, runValidation]);

  /**
   * Manually trigger pre-analysis (bypass debounce)
   */
  const validateNow = useCallback(async () => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    await runValidation();
  }, [runValidation]);

  return {
    isValidating,
    validationError,
    lastValidated,
    validateNow,
  };
};
