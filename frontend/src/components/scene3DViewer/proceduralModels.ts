import { createMechanisms, mechanismPose, positionMechanisms } from './mechanisms';
import * as THREE from 'three';
import type { Model3DConfig } from '@utils/sceneTypes';
import type { Scene3DController } from '@utils/Scene3DController';
import { sceneAppearance as appearance } from '../../styles/theme';
import type { SceneGeometry } from './sceneSpec';

export const CVT_MODEL_IDS = [
  'primaryFixed',
  'primaryMoving',
  'secondaryFixed',
  'secondaryMoving',
] as const;

function hubRadius(minRadius: number, geometry: SceneGeometry): number {
  return Math.max(minRadius - geometry.beltHeight, minRadius * 0.14);
}

function material(color: string): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color,
    metalness: appearance.metalness,
    roughness: appearance.roughness,
    side: THREE.DoubleSide,
  });
}

/** Revolved groove faces; hubs, rim thickness and witness marks are illustrative. */
function sheave(
  geometry: SceneGeometry,
  minimum: number,
  maximum: number,
  side: number,
  accent: string,
  shaft: boolean,
): THREE.Group {
  const group = new THREE.Group();
  const hub = hubRadius(minimum, geometry);
  const rim = maximum + geometry.beltHeight * 0.12;
  const thickness = rim * 0.055;
  const slope = Math.tan(geometry.halfAngle);
  const lip = (rim - hub) * slope;
  const profile = [
    [hub, 0],
    [rim, side * lip],
    [rim, side * (lip + thickness)],
    [hub, side * thickness],
    [hub, 0],
  ];
  const surface = new THREE.LatheGeometry(
    profile.map(([r, z]) => new THREE.Vector2(r, z)),
    appearance.radialSegments,
  );
  surface.rotateX(Math.PI / 2);
  group.add(new THREE.Mesh(surface, material(shaft ? appearance.fixedSheave : appearance.movingSheave)));

  const hubMesh = new THREE.Mesh(
    new THREE.CylinderGeometry(hub, hub, thickness * 2.5, 40),
    material(accent),
  );
  hubMesh.rotation.x = Math.PI / 2;
  hubMesh.position.z = side * thickness;
  group.add(hubMesh);
  const rimMesh = new THREE.Mesh(
    new THREE.TorusGeometry(
      rim,
      thickness * 0.28,
      8,
      appearance.radialSegments,
    ),
    material(accent),
  );
  rimMesh.position.z = side * (lip + thickness * 0.7);
  group.add(rimMesh);

  // A small back-face witness mark makes rigid-body rotation readable.
  const marker = new THREE.Mesh(
    new THREE.BoxGeometry(rim * 0.32, thickness * 0.6, thickness * 0.25),
    material(accent),
  );
  marker.position.set(
    rim * 0.76,
    0,
    side * ((rim * 0.76 - hub) * slope + thickness * 1.08),
  );
  marker.rotation.y = -side * geometry.halfAngle;
  group.add(marker);
  if (shaft) {
    const axle = new THREE.Mesh(
      new THREE.CylinderGeometry(
        hub * 0.52,
        hub * 0.52,
        geometry.beltOuterWidth + lip * 2 + thickness * 7,
        32,
      ),
      material(appearance.shaft),
    );
    axle.rotation.x = Math.PI / 2;
    group.add(axle);
  }
  return group;
}

export function createCVTModels(geometry: SceneGeometry): Model3DConfig[] {
  return [
    {
      id: 'primaryFixed',
      object3D: sheave(
        geometry,
        geometry.primaryMinRadius,
        geometry.primaryMaxRadius,
        -1,
        appearance.primary,
        true,
      ),
    },
    {
      id: 'primaryMoving',
      parentId: 'primaryFixed',
      object3D: sheave(
        geometry,
        geometry.primaryMinRadius,
        geometry.primaryMaxRadius,
        1,
        appearance.primary,
        false,
      ),
    },
    {
      id: 'secondaryFixed',
      object3D: sheave(
        geometry,
        geometry.secondaryMinRadius,
        geometry.secondaryMaxRadius,
        1,
        appearance.secondary,
        true,
      ),
    },
    {
      id: 'secondaryMoving',
      parentId: 'secondaryFixed',
      object3D: sheave(
        geometry,
        geometry.secondaryMinRadius,
        geometry.secondaryMaxRadius,
        -1,
        appearance.secondary,
        false,
      ),
    },
    ...createMechanisms(geometry),
  ];
}

export interface ScenePose {
  primaryRadius: number;
  secondaryRadius: number;
  primaryCenter: [number, number];
  secondaryCenter: [number, number];
  shift: number;
  beltZ: number;
  primaryAngle?: number;
  secondaryAngle?: number;
  helixAngle?: number;
}

/** Position groove faces around the supplied belt section; never solve belt closure. */
export function positionCVT(
  controller: Scene3DController,
  geometry: SceneGeometry,
  pose: ScenePose,
): void {
  const slope = Math.tan(geometry.halfAngle);
  const primaryGap =
    geometry.beltOuterWidth / 2 -
    (pose.primaryRadius - hubRadius(geometry.primaryMinRadius, geometry)) *
    slope;
  const secondaryGap =
    geometry.beltOuterWidth / 2 -
    (pose.secondaryRadius - hubRadius(geometry.secondaryMinRadius, geometry)) *
    slope;
  controller.updateModels({
    primaryFixed: {
      position: [...pose.primaryCenter, pose.beltZ - primaryGap],
      rotation: [0, 0, pose.primaryAngle ?? 0],
    },
    primaryMoving: {
      position: [
        0,
        0,
        2 * primaryGap + Math.max(0, geometry.deadzoneShift - pose.shift),
      ],
    },
    secondaryFixed: {
      position: [...pose.secondaryCenter, pose.beltZ + secondaryGap],
      rotation: [0, 0, pose.secondaryAngle ?? 0],
    },
    secondaryMoving: {
      position: [0, 0, -2 * secondaryGap],
      rotation: [0, 0, pose.helixAngle ?? mechanismPose(geometry, pose.shift)?.secondary_angle_rad ?? 0],
    },
  });
  positionMechanisms(controller, geometry, pose.shift);
}

export function fitCVT(
  controller: Scene3DController,
  geometry: SceneGeometry,
): void {
  const margin = geometry.beltHeight * 0.15;
  const radius =
    Math.max(geometry.primaryMaxRadius, geometry.secondaryMaxRadius) + margin;
  controller.fitBounds(
    new THREE.Box3(
      new THREE.Vector3(
        -geometry.centreDistance / 2 - geometry.primaryMaxRadius - margin,
        -radius,
        -radius * 0.7,
      ),
      new THREE.Vector3(
        geometry.centreDistance / 2 + geometry.secondaryMaxRadius + margin,
        radius,
        radius * 0.9,
      ),
    ),
  );
}
