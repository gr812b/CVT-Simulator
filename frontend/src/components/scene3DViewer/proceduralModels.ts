import {
  createMechanisms,
  mechanismLayout,
  mechanismPose,
  positionMechanisms,
  sheaveHub,
} from './mechanisms';
import { ring } from './mechanismGeometry';
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
  shaft: boolean,
  shaftRadius: number,
  shaftReach = 0,
): THREE.Group {
  const group = new THREE.Group();
  const hub = sheaveHub(minimum, geometry);
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
  group.add(
    new THREE.Mesh(
      surface,
      material(shaft ? appearance.fixedSheave : appearance.movingSheave),
    ),
  );

  const hubMesh = ring(
    shaft ? shaftRadius * 0.98 : shaftRadius * 1.02,
    hub,
    side * thickness - thickness * 1.25,
    side * thickness + thickness * 1.25,
    material(shaft ? appearance.fixedSheave : appearance.movingSheave),
  );
  group.add(hubMesh);
  const rimMesh = new THREE.Mesh(
    new THREE.TorusGeometry(
      rim,
      thickness * 0.28,
      8,
      appearance.radialSegments,
    ),
    material(shaft ? appearance.fixedSheave : appearance.movingSheave),
  );
  rimMesh.position.z = side * (lip + thickness * 0.7);
  group.add(rimMesh);

  // A small back-face witness mark makes rigid-body rotation readable.
  const marker = new THREE.Mesh(
    new THREE.BoxGeometry(rim * 0.32, thickness * 0.6, thickness * 0.25),
    material(shaft ? appearance.fixedSheave : appearance.movingSheave),
  );
  marker.position.set(
    rim * 0.76,
    0,
    side * ((rim * 0.76 - hub) * slope + thickness * 1.08),
  );
  marker.rotation.y = -side * geometry.halfAngle;
  group.add(marker);
  if (shaft) {
    // One continuous shaft joins the external boundary to the actuator carrier.
    const outerReach = maximum * appearance.shaftExtension + lip + thickness;
    const innerReach = Math.max(shaftReach, geometry.beltOuterWidth + lip);
    // Both boundary connections leave toward negative Z. On the secondary,
    // the shaft continues through the helix carrier before extending outward.
    const start = side < 0 ? -outerReach : -innerReach - outerReach;
    const end =
      side < 0 ? innerReach : Math.max(lip + thickness, thickness * 2.25);
    const axle = new THREE.Mesh(
      new THREE.CylinderGeometry(shaftRadius, shaftRadius, end - start, 32),
      material(appearance.shaft),
    );
    axle.rotation.x = Math.PI / 2;
    axle.name = 'boundary-shaft';
    axle.position.z = (start + end) / 2;
    group.add(axle);
  }
  return group;
}

export function createCVTModels(geometry: SceneGeometry, focus?: 'primary' | 'secondary'): Model3DConfig[] {
  if (focus) return [
    { id: `${focus}Fixed`, object3D: new THREE.Group() },
    { id: `${focus}Moving`, parentId: `${focus}Fixed`, object3D: new THREE.Group() },
    ...createMechanisms(geometry, focus),
  ];
  const layout = mechanismLayout(geometry);
  return [
    {
      id: 'primaryFixed',
      object3D: sheave(
        geometry,
        geometry.primaryMinRadius,
        geometry.primaryMaxRadius,
        -1,
        true,
        layout.shaftP,
        layout.carrierP,
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
        false,
        layout.shaftP,
      ),
    },
    {
      id: 'secondaryFixed',
      object3D: sheave(
        geometry,
        geometry.secondaryMinRadius,
        geometry.secondaryMaxRadius,
        1,
        true,
        layout.shaftS,
        -layout.baseS + layout.wall,
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
        false,
        layout.shaftS,
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
    (pose.primaryRadius - sheaveHub(geometry.primaryMinRadius, geometry)) *
      slope;
  const secondaryGap =
    geometry.beltOuterWidth / 2 -
    (pose.secondaryRadius - sheaveHub(geometry.secondaryMinRadius, geometry)) *
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
      rotation: [
        0,
        0,
        pose.helixAngle ??
          mechanismPose(geometry, pose.shift)?.secondary_angle_rad ??
          0,
      ],
    },
  });
  positionMechanisms(controller, geometry, pose.shift);
}

export function fitCVT(
  controller: Scene3DController,
  geometry: SceneGeometry,
): void {
  const margin = geometry.beltHeight * 0.3;
  const radius =
    Math.max(geometry.primaryMaxRadius, geometry.secondaryMaxRadius) + margin;
  const layout = mechanismLayout(geometry);
  const shaftEnvelope =
    appearance.shaftExtension + Math.tan(geometry.halfAngle) + 0.2;
  controller.fitBounds(
    new THREE.Box3(
      new THREE.Vector3(
        -geometry.centreDistance / 2 - geometry.primaryMaxRadius - margin,
        -radius,
        Math.min(
          -geometry.primaryMaxRadius * shaftEnvelope,
          layout.baseS -
            layout.wall * 2 -
            geometry.secondaryMaxRadius * shaftEnvelope,
        ),
      ),
      new THREE.Vector3(
        geometry.centreDistance / 2 + geometry.secondaryMaxRadius + margin,
        radius,
        Math.max(
          geometry.secondaryMaxRadius * (Math.tan(geometry.halfAngle) + 0.2),
          layout.carrierP + layout.wall,
        ),
      ),
    ),
  );
}
