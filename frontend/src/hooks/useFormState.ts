import { useState, useCallback, useRef } from 'react';
import { PARAMETERS, type Parameter, type ParameterState } from '@types';

export interface FormState {
  values: Record<Parameter, string>;
  errors: Record<Parameter, string | null>;
  touched: Record<Parameter, boolean>;
  hasChanges: boolean;
}

export const useFormState = () => {
  // Initialize form values with string representations of defaults
  const getInitialValues = useCallback((): Record<Parameter, string> => {
    return Object.entries(PARAMETERS).reduce((acc, [key, config]) => {
      acc[key as Parameter] = String(config.defaultValue);
      return acc;
    }, {} as Record<Parameter, string>);
  }, []);

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

  const [values, setValues] = useState<Record<Parameter, string>>(getInitialValues);
  const [errors, setErrors] = useState<Record<Parameter, string | null>>(getInitialErrors);
  const [touched, setTouched] = useState<Record<Parameter, boolean>>(getInitialTouched);
  const [hasChanges, setHasChanges] = useState(false);
  
  // Keep track of initial values for change detection
  const initialValuesRef = useRef<Record<Parameter, string>>(getInitialValues());

  // Update a field value and validate it
  const updateField = useCallback((parameter: Parameter, value: string) => {
    setValues(prev => ({ ...prev, [parameter]: value }));
    
    // Validate the field
    const validator = PARAMETERS[parameter].validate;
    const error = validator(value);
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
        result[parameterKey] = value.toLowerCase() === 'true';
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
    
    Object.keys(PARAMETERS).forEach(key => {
      const parameter = key as Parameter;
      const validator = PARAMETERS[parameter].validate;
      newErrors[parameter] = validator(values[parameter]);
    });
    
    setErrors(newErrors);
    setTouched(Object.keys(PARAMETERS).reduce((acc, key) => {
      acc[key as Parameter] = true;
      return acc;
    }, {} as Record<Parameter, boolean>));
    
    return Object.values(newErrors).every(error => error === null);
  }, [values]);

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
    resetForm,
    markAsSaved,
    validateAll,
  };
};