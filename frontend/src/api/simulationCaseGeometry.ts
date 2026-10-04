import type { SimulationCaseDocument } from './client';
import type { AssemblyGeometry } from './generated/assembly';
export type SimulationCaseGeometry = AssemblyGeometry;
export function simulationCaseGeometry(document: SimulationCaseDocument): SimulationCaseGeometry {
  return document.assembly.geometry as SimulationCaseGeometry;
}
