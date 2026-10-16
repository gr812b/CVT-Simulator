import * as THREE from 'three';
import type { SlidingBlockDemo, SlidingBlockFrame } from '@api/client';
import type { Model3DConfig } from '@utils/sceneTypes';
import type { Scene3DController } from '@utils/Scene3DController';
import { profileSolid } from '@components/scene3DViewer/mechanismGeometry';

type Point = readonly [number, number];
export const colors = {
  cup: '#718b9a',
  moving: '#b1bdc7',
  fixed: '#687480',
  shaft: '#8f9ca9',
  fixedTrack: '#2ed4b6',
  movingTrack: '#ff9864',
  block: '#e9bf68',
  belt: '#303842',
};
const angles = (count: number) =>
  Array.from({ length: count }, (_, i) => Math.PI + (2 * Math.PI * i) / count);
const material = (color: string) =>
  new THREE.MeshStandardMaterial({
    color,
    metalness: 0.3,
    roughness: 0.55,
    side: THREE.DoubleSide,
  });

function shape(points: readonly Point[]) {
  return new THREE.Shape(points.map(([r, z]) => new THREE.Vector2(r, z)));
}

function cutawayTrack(points: readonly Point[], color: string) {
  // Continue the track through the removed hardware at the front block's
  // meridional plane. These dashed curves explain its retained contacts.
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(
      points.map(([r, z]) => new THREE.Vector3(-r, 0, z))
    ),
    new THREE.LineDashedMaterial({
      color,
      dashSize: 0.0025,
      gapSize: 0.0015,
      transparent: true,
      opacity: 0.8,
    })
  );
  line.computeLineDistances();
  return line;
}

/** Physical r,z coordinates become a shaft along local +z. */
function revolve(
  points: readonly Point[],
  color: string,
  cutaway: boolean,
  solid = true
) {
  const group = new THREE.Group();
  const profile = solid ? [...points, points[0]] : [...points];
  const geometry = new THREE.LatheGeometry(
    profile.map(([r, z]) => new THREE.Vector2(r, z)),
    96,
    0,
    cutaway ? Math.PI : 2 * Math.PI
  );
  geometry.rotateX(Math.PI / 2);
  group.add(new THREE.Mesh(geometry, material(color)));
  if (solid && cutaway) {
    for (const angle of [-Math.PI / 2, Math.PI / 2]) {
      const cap = new THREE.ShapeGeometry(shape(points));
      cap.rotateX(Math.PI / 2);
      cap.rotateZ(angle);
      group.add(new THREE.Mesh(cap, material(color)));
    }
  }
  return group;
}

export function buildSlidingBlockModels(
  data: SlidingBlockDemo,
  cutaway: boolean
): Model3DConfig[] {
  const root = new THREE.Group();
  root.rotation.y = Math.PI / 2; // shaft horizontal; keep one r,z frame for every part
  const cup = revolve(data.cup_section_m, colors.cup, cutaway);
  cup.add(
    revolve(
      data.cup_track_m.map(([r, z]) => [r, z + 0.00006]),
      colors.fixedTrack,
      cutaway,
      false
    )
  );
  const moving = revolve(data.moving_section_m, colors.moving, cutaway);
  if (cutaway) {
    cup.add(cutawayTrack(data.cup_track_m, colors.fixedTrack));
    moving.add(cutawayTrack(data.moving_track_m, colors.movingTrack));
  }
  moving.add(
    revolve(
      data.moving_track_m.map(([r, z]) => [r, z - 0.00006]),
      colors.movingTrack,
      cutaway,
      false
    )
  );
  const shaftLength = data.shaft_limits_m[1] - data.shaft_limits_m[0];
  const shaft = new THREE.Mesh(
    new THREE.CylinderGeometry(
      data.shaft_radius_m,
      data.shaft_radius_m,
      shaftLength,
      48
    ),
    material(colors.shaft)
  );
  shaft.rotation.x = Math.PI / 2;
  shaft.position.z = (data.shaft_limits_m[1] + data.shaft_limits_m[0]) / 2;
  const blocks = new THREE.Group();
  for (const angle of angles(data.block_count)) {
    const block = new THREE.Group();
    block.rotation.z = angle;
    block.add(
      new THREE.Mesh(
        profileSolid(shape(data.block_outline_m), data.block_width_m),
        material(colors.block)
      )
    );
    blocks.add(block);
  }
  const contacts = new THREE.Group();
  for (const angle of angles(data.block_count)) {
    for (const [key, color] of [
      ['fixed', colors.fixedTrack],
      ['moving', colors.movingTrack],
    ] as const) {
      // The flat mating face has a contact span, not a known pressure point.
      const marker =
        key === 'fixed'
          ? new THREE.Mesh(
              new THREE.SphereGeometry(0.0012, 16, 12),
              new THREE.MeshBasicMaterial({ color })
            )
          : new THREE.Line(
              new THREE.BufferGeometry().setFromPoints([
                new THREE.Vector3(),
                new THREE.Vector3(),
              ]),
              new THREE.LineBasicMaterial({ color })
            );
      marker.userData = { angle, key, span: key === 'moving' };
      contacts.add(marker);
      const arrow = new THREE.ArrowHelper(
        new THREE.Vector3(0, 0, 1),
        new THREE.Vector3(),
        0.014,
        color,
        0.003,
        0.0015
      );
      arrow.userData = { angle, key };
      contacts.add(arrow);
    }
  }
  const com = new THREE.Mesh(
    new THREE.SphereGeometry(0.0015, 16, 12),
    new THREE.MeshBasicMaterial({ color: '#ffffff' })
  );
  return [
    { id: 'slidingRoot', object3D: root },
    { id: 'cup', parentId: 'slidingRoot', object3D: cup },
    { id: 'moving', parentId: 'slidingRoot', object3D: moving },
    {
      id: 'fixed',
      parentId: 'slidingRoot',
      object3D: revolve(data.fixed_section_m, colors.fixed, cutaway),
    },
    { id: 'shaft', parentId: 'slidingRoot', object3D: shaft },
    { id: 'blocks', parentId: 'slidingRoot', object3D: blocks },
    { id: 'contacts', parentId: 'slidingRoot', object3D: contacts },
    { id: 'com', parentId: 'slidingRoot', object3D: com },
    // The belt moves radially as well as axially, so its geometry is updated
    // from the shared frame, rather than inferred independently by the viewer.
    {
      id: 'sampleBelt',
      parentId: 'slidingRoot',
      object3D: revolve(data.frames[0].belt_section_m, colors.belt, cutaway),
    },
  ];
}

export function positionSlidingBlockModels(
  controller: Scene3DController,
  data: SlidingBlockDemo,
  frame: SlidingBlockFrame,
  showContacts: boolean
) {
  controller.getModel('blocks')?.object3D.children.forEach((block, i) => {
    const angle = angles(data.block_count)[i];
    block.position.set(
      frame.datum_m[0] * Math.cos(angle),
      frame.datum_m[0] * Math.sin(angle),
      frame.datum_m[1]
    );
  });
  const contacts = controller.getModel('contacts')?.object3D;
  if (contacts) {
    contacts.visible = showContacts;
    contacts.children.forEach((object) => {
      const { angle, key, span } = object.userData as {
        angle: number;
        key: 'fixed' | 'moving';
        span?: boolean;
      };
      if (span && object instanceof THREE.Line) {
        const positions = object.geometry.getAttribute('position');
        frame.moving_contact_span_m.forEach(([r, z], i) =>
          positions.setXYZ(i, r * Math.cos(angle), r * Math.sin(angle), z)
        );
        positions.needsUpdate = true;
        object.geometry.computeBoundingSphere();
        return;
      }
      const [a, b] = frame.moving_contact_span_m;
      // The arrow indicates only normal direction, anchored at face midpoint.
      const point =
        key === 'fixed'
          ? frame.fixed_contact_m
          : [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      const normal = key === 'fixed' ? frame.fixed_normal : frame.moving_normal;
      object.position.set(
        point[0] * Math.cos(angle),
        point[0] * Math.sin(angle),
        point[1]
      );
      if (object instanceof THREE.ArrowHelper)
        object.setDirection(
          new THREE.Vector3(
            normal[0] * Math.cos(angle),
            normal[0] * Math.sin(angle),
            normal[1]
          )
        );
    });
  }
  const com = controller.getModel('com')?.object3D;
  if (com) {
    com.visible = showContacts;
    com.position.set(-frame.com_m[0], 0, frame.com_m[1]);
  }
  controller.updateModels({ moving: { position: [0, 0, frame.closure_m] } });
}

export function updateSampleBelt(
  controller: Scene3DController,
  frame: SlidingBlockFrame,
  cutaway: boolean
) {
  const group = controller.getModel('sampleBelt')?.object3D;
  if (!group) return;
  // Reuse the model lifecycle for disposal of replaced GPU resources.
  controller.removeModel('sampleBelt');
  controller.addModel({
    id: 'sampleBelt',
    parentId: 'slidingRoot',
    object3D: revolve(frame.belt_section_m, colors.belt, cutaway),
  });
}
