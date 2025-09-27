import type { DataPoint2D, ValidationResult } from './types';

// Validation constants (moved from cvt_simulator.constants.ts)
export const VALIDATION = {
  MIN_DATA_POINTS_WARNING: 5,
  SINGLE_POINT_WARNING: 1,
  DATE_DETECTION_THRESHOLD: 0.8,
  HEADER_ROW_INDEX: 0,
  FIRST_DATA_ROW_INDEX: 1,
  NOT_FOUND_INDEX: -1,
} as const;

/**
 * Validates an array of data points
 */
export function validateData(data: DataPoint2D[]): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];
  
  // Check if data is an array
  if (!Array.isArray(data)) {
    return {
      isValid: false,
      errors: ['Data must be an array'],
      warnings: [],
    };
  }
  
  // Check if array is empty
  if (data.length === 0) {
    return {
      isValid: false,
      errors: ['Data array cannot be empty'],
      warnings: [],
    };
  }
  
  // Validate each data point
  data.forEach((point, index) => {
    if (typeof point !== 'object' || point === null) {
      errors.push(`Data point at index ${index} is not an object`);
      return;
    }
    
    if (!('x' in point) || !('y' in point)) {
      errors.push(`Data point at index ${index} missing x or y property`);
      return;
    }
    
    if (typeof point.y !== 'number' || !Number.isFinite(point.y)) {
      errors.push(`Data point at index ${index} has invalid y value`);
    }
    
    if (point.x === null || point.x === undefined) {
      errors.push(`Data point at index ${index} has null/undefined x value`);
    }
  });
  
  // Add warnings for data quality
  if (data.length === VALIDATION.SINGLE_POINT_WARNING) {
    warnings.push('Only one data point provided - chart may not display meaningfully');
  }
  
  if (data.length < VALIDATION.MIN_DATA_POINTS_WARNING) {
    warnings.push('Few data points provided - consider adding more for better visualization');
  }
  
  return {
    isValid: errors.length === 0,
    errors,
    warnings,
  };
}

/**
 * Converts arrays of x and y values to DataPoint2D array
 */
export function createDataFromArrays(
  xValues: (number | string | Date)[],
  yValues: number[]
): { data: DataPoint2D[]; validation: ValidationResult } {
  // Check if arrays have the same length
  if (xValues.length !== yValues.length) {
    return {
      data: [],
      validation: {
        isValid: false,
        errors: [`X and Y arrays have different lengths: ${xValues.length} vs ${yValues.length}`],
        warnings: [],
      },
    };
  }
  
  // Create data points
  const data: DataPoint2D[] = xValues.map((x, index) => ({
    x,
    y: yValues[index],
  }));
  
  // Validate the created data
  const validation = validateData(data);
  
  return { data, validation };
}

/**
 * Determines the appropriate axis type based on data
 */
export function inferAxisType(values: (number | string | Date)[]): 'time' | 'value' | 'category' {
  if (values.length === 0) return 'category';
  
  // Check if all values are numbers
  const numericCount = values.filter(v => typeof v === 'number' && Number.isFinite(v)).length;
  if (numericCount === values.length) {
    return 'value';
  }
  
  // Check if values are dates or date-like strings
  const dateCount = values.filter(v => {
    if (v instanceof Date) return true;
    if (typeof v === 'string') {
      const parsed = Date.parse(v);
      return Number.isFinite(parsed);
    }
    return false;
  }).length;
  
  const threshold = Math.max(1, Math.floor(values.length * VALIDATION.DATE_DETECTION_THRESHOLD));
  if (dateCount >= threshold) {
    return 'time';
  }
  
  return 'category';
}