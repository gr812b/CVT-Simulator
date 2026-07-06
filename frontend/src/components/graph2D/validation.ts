/**
 * Validation result for data
 */
interface ValidationResult {
  isValid: boolean;
  errors: string[];
  warnings: string[];
}

// Validation constants (moved from constants.ts)
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
export function validateData(xData: number[], yData: Array<Array<number | null>>): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];
  
  // Check if data is an array
  if (!Array.isArray(xData) || !Array.isArray(yData)) {
    return {
      isValid: false,
      errors: ['Data must be an array'],
      warnings: [],
    };
  }
  
  // Check if array is empty
  if (xData.length === 0 || yData.length === 0) {
    return {
      isValid: false,
      errors: ['Data array cannot be empty'],
      warnings: [],
    };
  }

  // Check if arrays have the same length
  if (xData.length !== yData.length) {
    return {
      isValid: false,
      errors: ['X and Y arrays must have the same length'],
      warnings: [],
    };
  }

  xData.forEach((x, index) => {
    if (typeof x !== 'number' || !Number.isFinite(x)) {
      errors.push(`X value at index ${index} is not a valid number`);
    }

    if (x === null || x === undefined) {
      errors.push(`X value at index ${index} has null/undefined value`);
    }
  });

  yData.forEach((y, index) => {
    for (const yValue of y) {
      // Null is an intentional report gap and is rendered by ECharts as a break
      // in the line. Non-finite numeric values remain invalid.
      if (yValue !== null && (typeof yValue !== 'number' || !Number.isFinite(yValue))) {
        errors.push(`Y value at index ${index} is not a valid number`);
      }
    }
  });
  
  // Add warnings for data quality
  if (xData.length === VALIDATION.SINGLE_POINT_WARNING) {
    warnings.push('Only one data point provided - chart may not display meaningfully');
  }

  if (xData.length < VALIDATION.MIN_DATA_POINTS_WARNING) {
    warnings.push('Few data points provided - consider adding more for better visualization');
  }
  
  return {
    isValid: errors.length === 0,
    errors,
    warnings,
  };
}