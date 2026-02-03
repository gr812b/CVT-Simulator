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
  } = data;

  const points: THREE.Vector3[] = [];

  // Pulleys spin around Z-axis, positioned along X-axis
  // Belt wraps in XY plane (perpendicular to Z)
  const primaryCenter = new THREE.Vector3(...primaryPosition);
  const secondaryCenter = new THREE.Vector3(...secondaryPosition);

  // Simple belt path: wrap around each pulley and connect with straight lines
  // For now, wrap π radians (180°) around each pulley
  const wrapAngle = Math.PI;
  const halfWrap = wrapAngle / 2;

  // Arc segments for smooth curves
  const arcSegments = 30;
  const spanSegments = 10;

  // 1. Arc around primary pulley: from -halfWrap to +halfWrap
  // Primary is flipped 180°, wrap from π/2 (top) to 3π/2 (bottom) going clockwise
  for (let i = 0; i <= arcSegments; i++) {
    const t = i / arcSegments;
    const angle = halfWrap + t * wrapAngle; // π/2 to 3π/2
    const x = primaryRadius * Math.cos(angle);
    const y = primaryRadius * Math.sin(angle);
    points.push(new THREE.Vector3(primaryCenter.x + x, primaryCenter.y + y, primaryCenter.z));
  }

  // 2. Straight line from primary bottom to secondary bottom
  const primaryBottomX = primaryRadius * Math.cos(halfWrap + wrapAngle); // 3π/2
  const primaryBottomY = primaryRadius * Math.sin(halfWrap + wrapAngle); // -Y
  const secondaryBottomX = secondaryRadius * Math.cos(-halfWrap); // -π/2 
  const secondaryBottomY = secondaryRadius * Math.sin(-halfWrap); // -Y

  const primaryBottom = new THREE.Vector3(primaryCenter.x + primaryBottomX, primaryCenter.y + primaryBottomY, primaryCenter.z);
  const secondaryBottom = new THREE.Vector3(secondaryCenter.x + secondaryBottomX, secondaryCenter.y + secondaryBottomY, secondaryCenter.z);

  for (let i = 1; i <= spanSegments; i++) {
    const t = i / spanSegments;
    points.push(new THREE.Vector3().lerpVectors(primaryBottom, secondaryBottom, t));
  }

  // 3. Arc around secondary pulley: from -halfWrap to +halfWrap (bottom to top)
  for (let i = 1; i <= arcSegments; i++) {
    const t = i / arcSegments;
    const angle = -halfWrap + t * wrapAngle; // -π/2 to π/2
    const x = secondaryRadius * Math.cos(angle);
    const y = secondaryRadius * Math.sin(angle);
    points.push(new THREE.Vector3(secondaryCenter.x + x, secondaryCenter.y + y, secondaryCenter.z));
  }

  // 4. Straight line from secondary top back to primary top
  const primaryTopX = primaryRadius * Math.cos(halfWrap); // π/2
  const primaryTopY = primaryRadius * Math.sin(halfWrap); // +Y
  const secondaryTopX = secondaryRadius * Math.cos(halfWrap); // π/2
  const secondaryTopY = secondaryRadius * Math.sin(halfWrap); // +Y

  const primaryTop = new THREE.Vector3(primaryCenter.x + primaryTopX, primaryCenter.y + primaryTopY, primaryCenter.z);
  const secondaryTop = new THREE.Vector3(secondaryCenter.x + secondaryTopX, secondaryCenter.y + secondaryTopY, secondaryCenter.z);

  for (let i = 1; i < spanSegments; i++) {
    const t = i / spanSegments;
    points.push(new THREE.Vector3().lerpVectors(secondaryTop, primaryTop, t));
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
  
  // Trapezoidal shape: narrower (top) on inside, wider (bottom) on outside
  // For V-belt in groove: small end toward pulley center, wide end away
  // Center at origin, with narrow end at -height/2 (inside) and wide end at +height/2 (outside)
  shape.moveTo(-topWidth / 2, -height / 2);  // Narrow inside
  shape.lineTo(topWidth / 2, -height / 2);
  shape.lineTo(bottomWidth / 2, height / 2);  // Wide outside
  shape.lineTo(-bottomWidth / 2, height / 2);
  shape.lineTo(-topWidth / 2, -height / 2);

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
