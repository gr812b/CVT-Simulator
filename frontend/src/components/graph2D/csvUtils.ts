import type { DataPoint2D } from './types';
import { createDataFromArrays } from './validation';
import { VALIDATION } from './constants';

/**
 * Simple CSV parser for basic comma-separated files (no quoted commas)
 */
export function parseCSVSimple(csvText: string): string[][] {
  return csvText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => line.split(',').map((cell) => cell.trim()));
}

/**
 * Converts CSV text to DataPoint2D array by finding specified columns
 */
export function csvToDataPoints(
  csvText: string,
  xColumnName: string,
  yColumnName: string
): {
  data: DataPoint2D[];
  errors: string[];
  warnings: string[];
} {
  const errors: string[] = [];
  const warnings: string[] = [];
  
  try {
    const rows = parseCSVSimple(csvText);
    
    if (rows.length < 2) {
      return {
        data: [],
        errors: ['CSV must have at least a header row and one data row'],
        warnings: [],
      };
    }
    
    // Find column indices (case-insensitive)
    const header = rows[VALIDATION.HEADER_ROW_INDEX].map(h => h.toLowerCase());
    const xIndex = header.indexOf(xColumnName.toLowerCase());
    const yIndex = header.indexOf(yColumnName.toLowerCase());
    
    if (xIndex === VALIDATION.NOT_FOUND_INDEX) {
      errors.push(`Column '${xColumnName}' not found in CSV header`);
    }
    
    if (yIndex === VALIDATION.NOT_FOUND_INDEX) {
      errors.push(`Column '${yColumnName}' not found in CSV header`);
    }
    
    if (errors.length > 0) {
      return { data: [], errors, warnings };
    }
    
    // Extract data
    const dataRows = rows.slice(VALIDATION.FIRST_DATA_ROW_INDEX);
    const xValues: (string | number)[] = [];
    const yValues: number[] = [];
    
    dataRows.forEach((row, index) => {
      if (row.length <= Math.max(xIndex, yIndex)) {
        warnings.push(`Row ${index + 2} has insufficient columns`);
        return;
      }
      
      const xRaw = row[xIndex];
      const yRaw = row[yIndex];
      
      if (!xRaw || !yRaw) {
        warnings.push(`Row ${index + 2} has empty values`);
        return;
      }
      
      // Parse Y value (must be numeric)
      const yValue = Number(yRaw);
      if (!Number.isFinite(yValue)) {
        warnings.push(`Row ${index + 2} has invalid Y value: '${yRaw}'`);
        return;
      }
      
      // Parse X value (can be numeric, date, or string)
      let xValue: string | number = xRaw;
      const numericX = Number(xRaw);
      if (Number.isFinite(numericX)) {
        xValue = numericX;
      }
      
      xValues.push(xValue);
      yValues.push(yValue);
    });
    
    // Convert to DataPoint2D format
    const { data, validation } = createDataFromArrays(xValues, yValues);
    
    return {
      data,
      errors: [...errors, ...validation.errors],
      warnings: [...warnings, ...validation.warnings],
    };
    
  } catch (error) {
    return {
      data: [],
      errors: [`Failed to parse CSV: ${error instanceof Error ? error.message : 'Unknown error'}`],
      warnings: [],
    };
  }
}

/**
 * Legacy function for backward compatibility - extracts 'time' and 'car_velocity' columns
 */
export function csvToVelocityData(csvText: string): {
  data: DataPoint2D[];
  errors: string[];
  warnings: string[];
} {
  return csvToDataPoints(csvText, 'time', 'car_velocity');
}

/**
 * Utility to get available column names from CSV
 */
export function getCSVColumns(csvText: string): string[] {
  try {
    const rows = parseCSVSimple(csvText);
    return rows.length > 0 ? rows[VALIDATION.HEADER_ROW_INDEX] : [];
  } catch {
    return [];
  }
}

/**
 * Checks if a value looks like a date/time
 */
export function isParsableDate(value: string): boolean {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp);
}

/**
 * Checks if a value is numeric
 */
export function isNumeric(value: string): boolean {
  return value !== '' && Number.isFinite(Number(value));
}