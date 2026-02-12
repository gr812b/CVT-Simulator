import { useState, useCallback, useRef } from 'react';
import { PARAMETERS, type Parameter, type ParameterState, type ParameterValue } from '@types';

export interface FormState {
  values: Record<Parameter, ParameterValue>;
  errors: Record<Parameter, string | null>;
  touched: Record<Parameter, boolean>;
  hasChanges: boolean;
}

export const useFormState = (contextValues?: ParameterState) => {
  // Initialize form values - strings for simple types, objects for complex types
  const getInitialValues = useCallback((): Record<Parameter, ParameterValue> => {
    return Object.entries(PARAMETERS).reduce((acc, [key, config]) => {
      const paramKey = key as Parameter;
      // Use context value if available, otherwise use default
      const value = contextValues?.[paramKey] ?? config.defaultValue;
      // Keep complex types as-is, convert primitives to strings for input fields
      acc[paramKey] = config.type === 'ramp' ? value : String(value);
      return acc;
    }, {} as Record<Parameter, ParameterValue>);
  }, [contextValues]);

  const getInitialErrors = useCallback((): Record<Parameter, string | null> => {
    return Object.keys(PARAMETERS).reduce((acc, key) => {
      acc[key as Parameter] = null;
      return acc;
    }, {} as Record<Parameter, string | null>);
  }, []);

  const getInitialTouched = useCallback((): Record<Parameter, boolean> => {
    return Object.keys(PARAMETERS).reduce((acc, key) => {
      acc[key as Parameter] = false;
      return acc;
    }, {} as Record<Parameter, boolean>);
  }, []);

  const [values, setValues] = useState<Record<Parameter, ParameterValue>>(() => getInitialValues());
  const [errors, setErrors] = useState<Record<Parameter, string | null>>(getInitialErrors);
  const [touched, setTouched] = useState<Record<Parameter, boolean>>(getInitialTouched);
  const [hasChanges, setHasChanges] = useState(false);
  
  // Keep track of initial values for change detection
  const initialValuesRef = useRef<Record<Parameter, ParameterValue>>(getInitialValues());

  // Update a field value and validate it
  const updateField = useCallback((parameter: Parameter, value: ParameterValue) => {
    console.log('[Field Validation] Updating field:', parameter, 'value:', value);
    
    setValues(prev => ({ ...prev, [parameter]: value }));
    
    // Validate the field (skip validation for complex types)
    const validator = PARAMETERS[parameter].validate;
    const error = validator ? validator(String(value)) : null;
    
    console.log('[Field Validation] Validation result for', parameter, ':', error ? `ERROR: ${error}` : 'VALID');
    
    setErrors(prev => ({ ...prev, [parameter]: error }));
    
    // Mark as touched
    setTouched(prev => ({ ...prev, [parameter]: true }));
    
    // Check if form has changes
    setHasChanges(() => {
      const newValues = { ...values, [parameter]: value };
      return Object.keys(PARAMETERS).some(key => 
        newValues[key as Parameter] !== initialValuesRef.current[key as Parameter]
      );
    });
  }, [values]);

  // Mark a field as touched (for focus events)
  const touchField = useCallback((parameter: Parameter) => {
    setTouched(prev => ({ ...prev, [parameter]: true }));
  }, []);

  // Get parsed values (convert strings to proper types)
  const getParsedValues = useCallback((): ParameterState => {
    const result = {} as Record<Parameter, unknown>;
    
    for (const [key, value] of Object.entries(values)) {
      const parameterKey = key as Parameter;
      const paramConfig = PARAMETERS[parameterKey];
      
      if (paramConfig.type === 'number') {
        result[parameterKey] = Number(value);
      } else if (paramConfig.type === 'string') {
        result[parameterKey] = value;
      } else if (paramConfig.type === 'boolean') {
        result[parameterKey] = typeof value === 'string' ? value.toLowerCase() === 'true' : Boolean(value);
      } else if (paramConfig.type === 'ramp') {
        // Keep ramp config as-is (already an object)
        result[parameterKey] = value;
      }
    }
    
    return result as ParameterState;
  }, [values]);

  // Check if form is valid
  const isValid = useCallback(() => {
    return Object.values(errors).every(error => error === null);
  }, [errors]);

  // Get fields that have been modified
  const getChangedFields = useCallback((): Parameter[] => {
    return Object.keys(PARAMETERS).filter(key => 
      values[key as Parameter] !== initialValuesRef.current[key as Parameter]
    ) as Parameter[];
  }, [values]);

  // Check if a specific field has been changed
  const isFieldChanged = useCallback((parameter: Parameter): boolean => {
    return values[parameter] !== initialValuesRef.current[parameter];
  }, [values]);

  // Reset form to initial state
  const resetForm = useCallback(() => {
    const initialValues = getInitialValues();
    setValues(initialValues);
    setErrors(getInitialErrors());
    setTouched(getInitialTouched());
    setHasChanges(false);
    initialValuesRef.current = initialValues;
  }, [getInitialValues, getInitialErrors, getInitialTouched]);

  // Mark form as saved (updates the baseline for change detection)
  const markAsSaved = useCallback(() => {
    setHasChanges(false);
    initialValuesRef.current = { ...values };
  }, [values]);

  // Validate all fields
  const validateAll = useCallback(() => {
    const newErrors: Record<Parameter, string | null> = {} as Record<Parameter, string | null>;
    
    Object.keys(PARAMETERS).forEach((key) => {
      const parameter = key as Parameter;
      const validator = PARAMETERS[parameter].validate;
      // Skip validation for fields without validators (like ramp)
      newErrors[parameter] = validator ? validator(String(values[parameter])) : null;
    });
    
    setErrors(newErrors);
    setTouched(Object.keys(PARAMETERS).reduce((acc, key) => {
      acc[key as Parameter] = true;
      return acc;
    }, {} as Record<Parameter, boolean>));
    
    return Object.values(newErrors).every(error => error === null);
  }, [values]);

  // Reset form to specific values (e.g., baseline parameters)
  const resetToValues = useCallback((newValues: ParameterState) => {
    const formattedValues = Object.entries(PARAMETERS).reduce((acc, [key, config]) => {
      const paramKey = key as Parameter;
      const value = newValues[paramKey] ?? config.defaultValue;
      // Keep complex types as-is, convert primitives to strings for input fields
      acc[paramKey] = config.type === 'ramp' ? value : String(value);
      return acc;
    }, {} as Record<Parameter, ParameterValue>);
    
    setValues(formattedValues);
    setErrors(getInitialErrors());
    setTouched(getInitialTouched());
    setHasChanges(false);
    initialValuesRef.current = formattedValues;
  }, [getInitialErrors, getInitialTouched]);

  return {
    values,
    errors,
    touched,
    hasChanges,
    updateField,
    touchField,
    getParsedValues,
    isValid,
    getChangedFields,
    isFieldChanged,
    resetForm,
    resetToValues,
    markAsSaved,
    validateAll,
  };
};