import type { RunResponse } from '@utils/api';

/**
 * Example utility functions to extract data for graphing from simulation results
 */

export interface TimeSeriesPoint {
  time: number;
  value: number;
}

export interface GraphDataSet {
  label: string;
  data: TimeSeriesPoint[];
  color?: string;
}

/**
 * Extract car velocity over time for graphing
 */
export const extractCarVelocityData = (simulationResult: RunResponse): GraphDataSet => {
  return {
    label: 'Car Velocity (m/s)',
    data: simulationResult.data.map(point => ({
      time: point.time,
      value: point.state.car_velocity
    })),
    color: '#3b82f6' // blue
  };
};

/**
 * Extract car position over time for graphing
 */
export const extractCarPositionData = (simulationResult: RunResponse): GraphDataSet => {
  return {
    label: 'Car Position (m)',
    data: simulationResult.data.map(point => ({
      time: point.time,
      value: point.state.car_position
    })),
    color: '#10b981' // green
  };
};

/**
 * Extract CVT shift distance over time for graphing
 */
export const extractShiftDistanceData = (simulationResult: RunResponse): GraphDataSet => {
  return {
    label: 'Shift Distance (m)',
    data: simulationResult.data.map(point => ({
      time: point.time,
      value: point.state.shift_distance
    })),
    color: '#f59e0b' // amber
  };
};

/**
 * Extract engine power over time for graphing
 */
export const extractEnginePowerData = (simulationResult: RunResponse): GraphDataSet => {
  return {
    label: 'Engine Power (W)',
    data: simulationResult.data.map(point => ({
      time: point.time,
      value: point.car_state.engine_forces.power
    })),
    color: '#ef4444' // red
  };
};

/**
 * Extract all common graph datasets
 */
export const extractAllGraphData = (simulationResult: RunResponse): GraphDataSet[] => {
  return [
    extractCarVelocityData(simulationResult),
    extractCarPositionData(simulationResult),
    extractShiftDistanceData(simulationResult),
    extractEnginePowerData(simulationResult),
  ];
};