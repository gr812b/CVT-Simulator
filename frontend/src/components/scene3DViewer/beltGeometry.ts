import * as THREE from 'three';
import type { SceneGeometry } from './sceneSpec';

export interface BeltPathData {
  primaryRadius: number;
  primaryPosition: [number, number, number];
  secondaryRadius: number;
  secondaryPosition: [number, number, number];
  primaryWrapAngle?: number;
  secondaryWrapAngle?: number;
}

export const calculateBeltPath = (data: BeltPathData): THREE.CatmullRomCurve3 => {
  const primary = new THREE.Vector3(...data.primaryPosition); const secondary = new THREE.Vector3(...data.secondaryPosition);
  const primaryHalf = (data.primaryWrapAngle ?? Math.PI) / 2; const secondaryHalf = (data.secondaryWrapAngle ?? Math.PI) / 2;
  const points: THREE.Vector3[] = []; const arcSegments = 30; const spanSegments = 10;
  for (let index = 0; index <= arcSegments; index += 1) { const angle = Math.PI + primaryHalf - index / arcSegments * primaryHalf * 2; points.push(new THREE.Vector3(primary.x + data.primaryRadius * Math.cos(angle), primary.y + data.primaryRadius * Math.sin(angle), primary.z)); }
  const primaryTop = new THREE.Vector3(primary.x + data.primaryRadius * Math.cos(Math.PI - primaryHalf), primary.y + data.primaryRadius * Math.sin(Math.PI - primaryHalf), primary.z);
  const secondaryTop = new THREE.Vector3(secondary.x + data.secondaryRadius * Math.cos(secondaryHalf), secondary.y + data.secondaryRadius * Math.sin(secondaryHalf), secondary.z);
  for (let index = 1; index <= spanSegments; index += 1) points.push(new THREE.Vector3().lerpVectors(primaryTop, secondaryTop, index / spanSegments));
  for (let index = 1; index <= arcSegments; index += 1) { const angle = secondaryHalf - index / arcSegments * secondaryHalf * 2; points.push(new THREE.Vector3(secondary.x + data.secondaryRadius * Math.cos(angle), secondary.y + data.secondaryRadius * Math.sin(angle), secondary.z)); }
  const primaryBottom = new THREE.Vector3(primary.x + data.primaryRadius * Math.cos(Math.PI + primaryHalf), primary.y + data.primaryRadius * Math.sin(Math.PI + primaryHalf), primary.z);
  const secondaryBottom = new THREE.Vector3(secondary.x + data.secondaryRadius * Math.cos(-secondaryHalf), secondary.y + data.secondaryRadius * Math.sin(-secondaryHalf), secondary.z);
  for (let index = 1; index < spanSegments; index += 1) points.push(new THREE.Vector3().lerpVectors(secondaryBottom, primaryBottom, index / spanSegments));
  return new THREE.CatmullRomCurve3(points, true);
};

const crossSection = (geometry: SceneGeometry): THREE.Shape => {
  const shape = new THREE.Shape(); const outer = geometry.beltOuterWidth; const inner = geometry.beltInnerWidth; const height = geometry.beltHeight;
  shape.moveTo(-outer / 2, -height / 2); shape.lineTo(outer / 2, -height / 2); shape.lineTo(inner / 2, height / 2); shape.lineTo(-inner / 2, height / 2); shape.lineTo(-outer / 2, -height / 2);
  return shape;
};

export const createBeltMesh = (curve: THREE.CatmullRomCurve3, geometry: SceneGeometry): THREE.Mesh => new THREE.Mesh(new THREE.ExtrudeGeometry(crossSection(geometry), { extrudePath: curve, steps: 100, bevelEnabled: false }), new THREE.MeshPhysicalMaterial({ color: 0x1a1a1a, metalness: 0.1, roughness: 0.8, clearcoat: 0.1, clearcoatRoughness: 0.8 }));
export const updateBeltMesh = (mesh: THREE.Mesh, data: BeltPathData, geometry: SceneGeometry): void => { mesh.geometry.dispose(); mesh.geometry = new THREE.ExtrudeGeometry(crossSection(geometry), { extrudePath: calculateBeltPath(data), steps: 100, bevelEnabled: false }); };
