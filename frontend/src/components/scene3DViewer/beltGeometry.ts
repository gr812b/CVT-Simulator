import * as THREE from 'three';
import type { ConstantsResponse } from '@utils/api';

/**
 * Data needed to calculate belt path at any given moment
 */
export interface BeltPathData {
  primaryRadius: number;
  primaryPosition: [number, number, number];
  secondaryRadius: number;
  secondaryPosition: [number, number, number];
  primaryWrapAngle?: number; // Wrap angle in radians
  secondaryWrapAngle?: number; // Wrap angle in radians
}

/**
 * Calculate the belt path as a 3D curve.
 * 
 * The belt wraps around two pulleys:
 * 1. Arc around primary pulley (driven by engine)
 * 2. Straight tangent span from primary to secondary
 * 3. Arc around secondary pulley (drives wheels)
 * 4. Straight tangent span from secondary back to primary
 * 
 * @param data Belt path data including pulley radii, positions, and wrap angles
 * @returns THREE.CatmullRomCurve3 representing the belt path
 */
export const calculateBeltPath = (data: BeltPathData): THREE.CatmullRomCurve3 => {
  const {
    primaryRadius,
    primaryPosition,
    secondaryRadius,
    secondaryPosition,
    primaryWrapAngle = Math.PI,
    secondaryWrapAngle = Math.PI,
  } = data;

  const points: THREE.Vector3[] = [];

  // Pulleys spin around Z-axis, positioned along X-axis
  // Belt wraps in XY plane (perpendicular to Z)
  const primaryCenter = new THREE.Vector3(...primaryPosition);
  const secondaryCenter = new THREE.Vector3(...secondaryPosition);

  // Simple belt path: wrap around each pulley and connect with straight lines
  // Wrap angles are centered on the far side (away from the other pulley)
  // For non-crossing belt: +Y to +Y, -Y to -Y
  // Primary (left, -X): centered at π radians (left side, away from secondary)
  // Secondary (right, +X): centered at 0 radians (right side, away from primary)
  const primaryHalfWrap = primaryWrapAngle / 2;
  const secondaryHalfWrap = secondaryWrapAngle / 2;

  // Arc segments for smooth curves
  const arcSegments = 30;
  const spanSegments = 10;

  // 1. Arc around primary pulley: centered at π, wraps ±halfWrap
  // Start from bottom (π + halfWrap, -Y) going counterclockwise to top (π - halfWrap, +Y)
  for (let i = 0; i <= arcSegments; i++) {
    const t = i / arcSegments;
    const angle = Math.PI + primaryHalfWrap - t * primaryWrapAngle;
    const x = primaryRadius * Math.cos(angle);
    const y = primaryRadius * Math.sin(angle);
    points.push(new THREE.Vector3(primaryCenter.x + x, primaryCenter.y + y, primaryCenter.z));
  }

  // 2. Straight line from primary top (+Y) to secondary top (+Y) - non-crossing
  const primaryTopAngle = Math.PI - primaryHalfWrap;  // +Y side
  const secondaryTopAngle = secondaryHalfWrap;  // +Y side
  
  const primaryTopX = primaryRadius * Math.cos(primaryTopAngle);
  const primaryTopY = primaryRadius * Math.sin(primaryTopAngle);
  const secondaryTopX = secondaryRadius * Math.cos(secondaryTopAngle);
  const secondaryTopY = secondaryRadius * Math.sin(secondaryTopAngle);

  const primaryTop = new THREE.Vector3(primaryCenter.x + primaryTopX, primaryCenter.y + primaryTopY, primaryCenter.z);
  const secondaryTop = new THREE.Vector3(secondaryCenter.x + secondaryTopX, secondaryCenter.y + secondaryTopY, secondaryCenter.z);

  for (let i = 1; i <= spanSegments; i++) {
    const t = i / spanSegments;
    points.push(new THREE.Vector3().lerpVectors(primaryTop, secondaryTop, t));
  }

  // 3. Arc around secondary pulley: centered at 0, wraps ±halfWrap
  // Start from top (+halfWrap, +Y) going counterclockwise to bottom (-halfWrap, -Y)
  for (let i = 1; i <= arcSegments; i++) {
    const t = i / arcSegments;
    const angle = secondaryHalfWrap - t * secondaryWrapAngle;
    const x = secondaryRadius * Math.cos(angle);
    const y = secondaryRadius * Math.sin(angle);
    points.push(new THREE.Vector3(secondaryCenter.x + x, secondaryCenter.y + y, secondaryCenter.z));
  }

  // 4. Straight line from secondary bottom (-Y) back to primary bottom (-Y) - non-crossing
  const primaryBottomAngle = Math.PI + primaryHalfWrap;  // -Y side
  const secondaryBottomAngle = -secondaryHalfWrap;  // -Y side
  
  const primaryBottomX = primaryRadius * Math.cos(primaryBottomAngle);
  const primaryBottomY = primaryRadius * Math.sin(primaryBottomAngle);
  const secondaryBottomX = secondaryRadius * Math.cos(secondaryBottomAngle);
  const secondaryBottomY = secondaryRadius * Math.sin(secondaryBottomAngle);

  const primaryBottom = new THREE.Vector3(primaryCenter.x + primaryBottomX, primaryCenter.y + primaryBottomY, primaryCenter.z);
  const secondaryBottom = new THREE.Vector3(secondaryCenter.x + secondaryBottomX, secondaryCenter.y + secondaryBottomY, secondaryCenter.z);

  for (let i = 1; i < spanSegments; i++) {
    const t = i / spanSegments;
    points.push(new THREE.Vector3().lerpVectors(secondaryBottom, primaryBottom, t));
  }

  // Create closed curve
  return new THREE.CatmullRomCurve3(points, true);
};

/**
 * Create a trapezoidal cross-section shape for the V-belt.
 * 
 * @param constants Simulator constants containing belt dimensions
 * @param scale Scale factor for the cross-section (default 1)
 * @returns THREE.Shape representing the belt cross-section
 */
export const createBeltCrossSection = (constants: ConstantsResponse, scale: number = 1): THREE.Shape => {
  const topWidth = constants.belt_width_top * scale;
  const bottomWidth = constants.belt_width_bottom * scale;
  const height = constants.belt_height * scale;

  const shape = new THREE.Shape();
  
  // Trapezoidal shape: wider (bottom) at -height/2, narrower (top) at +height/2
  // For V-belt in groove: narrow end (top) is inside toward pulley center, wide end (bottom) is outside away from center
  // Center at origin
  shape.moveTo(-bottomWidth / 2, -height / 2);  // Bottom left (wider, outside)
  shape.lineTo(bottomWidth / 2, -height / 2);   // Bottom right (wider, outside)
  shape.lineTo(topWidth / 2, height / 2);        // Top right (narrower, inside)
  shape.lineTo(-topWidth / 2, height / 2);       // Top left (narrower, inside)
  shape.lineTo(-bottomWidth / 2, -height / 2);   // Close shape

  return shape;
};

/**
 * Create a belt mesh from a belt path curve.
 * 
 * @param curve Belt path curve
 * @param constants Simulator constants
 * @param scale Scale factor for belt thickness
 * @returns THREE.Mesh representing the belt
 */
export const createBeltMesh = (
  curve: THREE.CatmullRomCurve3,
  constants: ConstantsResponse,
  scale: number = 1
): THREE.Mesh => {
  // Create cross-section shape
  const shape = createBeltCrossSection(constants, scale);
  
  // Create tube geometry along the curve
  const tubeGeometry = new THREE.ExtrudeGeometry(shape, {
    extrudePath: curve,
    steps: 100,
    bevelEnabled: false,
  });

  // Create material for the belt
  const beltMaterial = new THREE.MeshPhysicalMaterial({
    color: 0x1a1a1a, // Black rubber color
    metalness: 0.1,
    roughness: 0.8,
    clearcoat: 0.1,
    clearcoatRoughness: 0.8,
  });

  const beltMesh = new THREE.Mesh(tubeGeometry, beltMaterial);
  beltMesh.castShadow = true;
  beltMesh.receiveShadow = true;

  return beltMesh;
};

/**
 * Update an existing belt mesh with new path data.
 * Replaces the geometry with a new one calculated from updated path data.
 * 
 * @param beltMesh Existing belt mesh to update
 * @param data New belt path data
 * @param constants Simulator constants
 * @param scale Scale factor for belt thickness
 */
export const updateBeltMesh = (
  beltMesh: THREE.Mesh,
  data: BeltPathData,
  constants: ConstantsResponse,
  scale: number = 1
): void => {
  // Dispose old geometry
  if (beltMesh.geometry) {
    beltMesh.geometry.dispose();
  }

  // Calculate new path
  const curve = calculateBeltPath(data);
  const shape = createBeltCrossSection(constants, scale);

  // Create new geometry
  const newGeometry = new THREE.ExtrudeGeometry(shape, {
    extrudePath: curve,
    steps: 100,
    bevelEnabled: false,
  });

  beltMesh.geometry = newGeometry;
};
