import * as THREE from 'three';
import type { Model3DConfig } from '@utils/sceneTypes';
import type { Scene3DController } from '@utils/Scene3DController';
import { sceneAppearance as appearance } from '../../styles/theme';
import { sceneDistance, type SceneGeometry } from './sceneSpec';

const yAxis = new THREE.Vector3(0, 1, 0);
const metal = (color: string) => new THREE.MeshStandardMaterial({ color, metalness: 0.45, roughness: 0.45 });
const point = ([axial, radial]: readonly number[], back: number) => new THREE.Vector3(sceneDistance(radial), 0, back - sceneDistance(axial));

export function mechanismPose(geometry: SceneGeometry, shift: number) {
  const poses = geometry.mechanisms?.poses;
  if (!poses?.length) return null;
  const index = poses.findIndex(p => sceneDistance(p.shift_m) >= shift);
  if (index <= 0) return index < 0 ? poses.at(-1)! : poses[0];
  const a = poses[index - 1], b = poses[index];
  const alpha = (shift - sceneDistance(a.shift_m)) / sceneDistance(b.shift_m - a.shift_m);
  const lerp = (x: number, y: number) => THREE.MathUtils.lerp(x, y, alpha);
  return {
    ...a, primary_ramp_shift_m: lerp(a.primary_ramp_shift_m, b.primary_ramp_shift_m),
    secondary_angle_rad: lerp(a.secondary_angle_rad, b.secondary_angle_rad),
    primary_roller_m: a.primary_roller_m && b.primary_roller_m
      ? [lerp(a.primary_roller_m[0], b.primary_roller_m[0]), lerp(a.primary_roller_m[1], b.primary_roller_m[1])] : null
  };
}

export function createMechanisms(geometry: SceneGeometry): Model3DConfig[] {
  const spec = geometry.mechanisms;
  if (!spec) return [];
  const models: Model3DConfig[] = [];
  if (spec.primary) {
    const root = new THREE.Group();
    const back = geometry.beltOuterWidth * 1.2 + geometry.maxShift * 1.4;
    for (let i = 0; i < Math.min(12, spec.primary.count); i++) {
      const group = new THREE.Group();
      group.rotation.z = i * Math.PI * 2 / spec.primary.count;
      const pivot = new THREE.Mesh(new THREE.SphereGeometry(0.09, 12, 8), metal(appearance.shaft));
      pivot.position.copy(point(spec.primary.pivot_m, back));
      const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.065, 0.09, 1, 12), metal(appearance.flyweight));
      arm.name = 'arm';
      const radius = sceneDistance(spec.primary.roller_radius_m);
      const roller = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, radius * 0.8, 24), metal(appearance.roller));
      roller.name = 'roller';
      const ramp = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(spec.primary.ramp_points_m.map(p => point(p, back))), 80, 0.045, 8, false), metal(appearance.ramp));
      ramp.name = 'ramp';
      group.add(pivot, arm, roller, ramp); root.add(group);
    }
    models.push({ id: 'flyweights', parentId: 'primaryFixed', object3D: root });
  }
  if (spec.secondary_helix_points_m.length) {
    const helix = new THREE.Group();
    const path = spec.secondary_helix_points_m.map(([x, y, z]) => new THREE.Vector3(sceneDistance(x), sceneDistance(y), -geometry.beltOuterWidth - sceneDistance(z)));
    const rail = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(path), 80, 0.065, 8, false);
    for (let i = 0; i < 3; i++) {
      const track = new THREE.Mesh(rail, metal(appearance.helix)); track.rotation.z = i * Math.PI * 2 / 3;
      helix.add(track);
    }
    models.push({ id: 'helix', parentId: 'secondaryFixed', object3D: helix });
    const followers = new THREE.Group();
    const [x, y] = spec.secondary_helix_points_m[0];
    const hub = Math.max(geometry.secondaryMinRadius - geometry.beltHeight, geometry.secondaryMinRadius * 0.14);
    const initialGap = geometry.beltOuterWidth / 2 - (geometry.secondaryMaxRadius - hub) * Math.tan(geometry.halfAngle);
    for (let i = 0; i < 3; i++) {
      const follower = new THREE.Mesh(new THREE.SphereGeometry(0.12, 12, 8), metal(appearance.roller));
      const theta = i * Math.PI * 2 / 3;
      follower.position.set(sceneDistance(x) * Math.cos(theta) - sceneDistance(y) * Math.sin(theta),
        sceneDistance(x) * Math.sin(theta) + sceneDistance(y) * Math.cos(theta), -geometry.beltOuterWidth + 2 * initialGap);
      followers.add(follower);
    }
    models.push({ id: 'helixFollowers', parentId: 'secondaryMoving', object3D: followers });
  }
  return models;
}

export function positionMechanisms(controller: Scene3DController, geometry: SceneGeometry, shift: number) {
  const spec = geometry.mechanisms?.primary, pose = mechanismPose(geometry, shift);
  if (!spec || !pose?.primary_roller_m) return;
  const root = controller.getModel('flyweights')?.object3D;
  const back = geometry.beltOuterWidth * 1.2 + geometry.maxShift * 1.4;
  const pivot = point(spec.pivot_m, back), roller = point(pose.primary_roller_m, back);
  const direction = roller.clone().sub(pivot);
  root?.children.forEach(group => {
    const arm = group.getObjectByName('arm')!;
    arm.position.copy(pivot).add(roller).multiplyScalar(0.5);
    arm.quaternion.setFromUnitVectors(yAxis, direction.clone().normalize());
    arm.scale.y = direction.length();
    group.getObjectByName('roller')!.position.copy(roller);
    group.getObjectByName('ramp')!.position.z = -sceneDistance(pose.primary_ramp_shift_m);
  });
}
