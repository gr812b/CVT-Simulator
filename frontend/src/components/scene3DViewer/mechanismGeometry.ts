import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { sceneAppearance as appearance } from '../../styles/theme';

const zAxis = new THREE.Vector3(0, 0, 1);

export function metal(color: string): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color,
    metalness: appearance.metalness,
    roughness: appearance.roughness,
    side: THREE.DoubleSide,
  });
}

export function beam(
  a: THREE.Vector3,
  b: THREE.Vector3,
  width: number,
  material: THREE.Material,
): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(width, width, 1), material);
  positionBeam(mesh, a, b);
  return mesh;
}

export function positionBeam(
  mesh: THREE.Object3D,
  a: THREE.Vector3,
  b: THREE.Vector3,
): void {
  const direction = b.clone().sub(a);
  mesh.position.copy(a).add(b).multiplyScalar(0.5);
  mesh.quaternion.setFromUnitVectors(zAxis, direction.clone().normalize());
  mesh.scale.z = direction.length();
}

export function cylinder(
  radius: number,
  length: number,
  material: THREE.Material,
): THREE.Mesh {
  const geometry = new THREE.CylinderGeometry(radius, radius, length, 24);
  geometry.rotateX(Math.PI / 2);
  return new THREE.Mesh(geometry, material);
}

export function ring(
  inner: number,
  outer: number,
  start: number,
  end: number,
  material: THREE.Material,
): THREE.Mesh {
  const profile = [
    [inner, start],
    [outer, start],
    [outer, end],
    [inner, end],
    [inner, start],
  ];
  const geometry = new THREE.LatheGeometry(
    profile.map(([r, z]) => new THREE.Vector2(r, z)),
    48,
  );
  // Lathe's y axis becomes +z, matching the rest of the mechanism geometry.
  geometry.rotateX(Math.PI / 2);
  return new THREE.Mesh(geometry, material);
}

function normalAt(points: THREE.Vector2[], index: number): THREE.Vector2 {
  const tangent = points[Math.min(index + 1, points.length - 1)]
    .clone()
    .sub(points[Math.max(0, index - 1)])
    .normalize();
  return new THREE.Vector2(-tangent.y, tangent.x);
}

/** Extrude the contact profile away from the roller into a solid ramp. */
export function rampSolid(
  points: THREE.Vector2[],
  side: number,
  depth: number,
  width: number,
): THREE.BufferGeometry {
  const back = points.map((p, i) =>
    p.clone().addScaledVector(normalAt(points, i), -side * depth),
  );
  const shape = new THREE.Shape([...points, ...back.reverse()]);
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth: width,
    bevelEnabled: false,
    steps: 1,
  });
  const position = geometry.getAttribute('position');
  for (let i = 0; i < position.count; i++) {
    const radial = position.getX(i),
      axial = position.getY(i),
      across = position.getZ(i);
    position.setXYZ(i, radial, across - width / 2, axial);
  }
  geometry.computeVertexNormals();
  return geometry;
}

function slotOutline(path: THREE.Vector2[], radius: number): THREE.Vector2[] {
  const left = path.map((p, i) =>
    p.clone().addScaledVector(normalAt(path, i), radius),
  );
  const right = path.map((p, i) =>
    p.clone().addScaledVector(normalAt(path, i), -radius),
  );
  const cap = (index: number, start: number) => {
    const center = path[index],
      normal = normalAt(path, index);
    const angle = Math.atan2(normal.y, normal.x) + start;
    return Array.from(
      { length: 13 },
      (_, i) =>
        new THREE.Vector2(
          center.x + radius * Math.cos(angle - (i * Math.PI) / 12),
          center.y + radius * Math.sin(angle - (i * Math.PI) / 12),
        ),
    );
  };
  return [
    ...left,
    ...cap(path.length - 1, 0),
    ...right.reverse(),
    ...cap(0, Math.PI),
  ];
}

/** A real annular wall with rounded through-slots, built in unwrapped (rθ,z).
 * Subdivision before wrapping avoids large flat chords across the cylinder.
 */
export function slottedSleeve(
  radius: number,
  wall: number,
  path: THREE.Vector2[],
  rollerRadius: number,
  start: number,
  end: number,
  count: number,
): THREE.BufferGeometry {
  const half = (Math.PI * radius) / count;
  // Follow the slot with the panel seam. A steep helix can cross a conventional
  // 120° rectangular panel boundary while its three tracks remain separate.
  const ordered = [...path].sort((a, b) => a.y - b.y);
  const boundary = (side: number) => [
    new THREE.Vector2(ordered[0].x + side * half, start),
    ...ordered.map((p) => new THREE.Vector2(p.x + side * half, p.y)),
    new THREE.Vector2(ordered.at(-1)!.x + side * half, end),
  ];
  const shape = new THREE.Shape([...boundary(-1), ...boundary(1).reverse()]);
  shape.holes.push(new THREE.Path(slotOutline(path, rollerRadius)));
  const flat = new THREE.ExtrudeGeometry(shape, {
    depth: wall,
    bevelEnabled: false,
    steps: 1,
  });
  const source = flat.getAttribute('position');
  const vertices: number[] = [],
    normals: number[] = [];
  const faceNormal = new THREE.Vector3();
  const wrap = (p: THREE.Vector3) => {
    const angle = p.x / radius,
      r = radius + p.z - wall / 2;
    vertices.push(r * Math.cos(angle), r * Math.sin(angle), p.y);
    const tangent = (faceNormal.x * radius) / r;
    const normal = new THREE.Vector3(
      faceNormal.z * Math.cos(angle) - tangent * Math.sin(angle),
      faceNormal.z * Math.sin(angle) + tangent * Math.cos(angle),
      faceNormal.y,
    ).normalize();
    normals.push(normal.x, normal.y, normal.z);
  };
  const subdivide = (
    a: THREE.Vector3,
    b: THREE.Vector3,
    c: THREE.Vector3,
  ): void => {
    const edges = [
      Math.abs(a.x - b.x),
      Math.abs(b.x - c.x),
      Math.abs(c.x - a.x),
    ];
    const longest = Math.max(...edges);
    if (longest <= radius * appearance.mechanism.maxPanelAngle) {
      wrap(a);
      wrap(b);
      wrap(c);
      return;
    }
    const edge = edges.indexOf(longest);
    const [p, q, r] =
      edge === 0 ? [a, b, c] : edge === 1 ? [b, c, a] : [c, a, b];
    const m = p.clone().add(q).multiplyScalar(0.5);
    subdivide(p, m, r);
    subdivide(m, q, r);
  };
  for (let i = 0; i < source.count; i += 3) {
    faceNormal.fromBufferAttribute(flat.getAttribute('normal'), i);
    subdivide(
      ...([0, 1, 2].map((j) =>
        new THREE.Vector3().fromBufferAttribute(source, i + j),
      ) as [THREE.Vector3, THREE.Vector3, THREE.Vector3]),
    );
  }
  flat.dispose();
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute(vertices, 3),
  );
  geometry.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));
  return geometry;
}

/** Batch rigid hardware by material, retaining named shell surfaces for ghosting. */
export function batchRigidParts(root: THREE.Group): THREE.Group {
  root.updateMatrixWorld(true);
  const batches = new Map<
    string,
    { material: THREE.Material; name: string; parts: THREE.BufferGeometry[] }
  >();
  const originals = new Set<THREE.BufferGeometry>();
  root.traverse((object) => {
    if (!(object instanceof THREE.Mesh) || Array.isArray(object.material))
      return;
    const key = object.material.uuid + object.name;
    let batch = batches.get(key);
    if (!batch) {
      batch = { material: object.material, name: object.name, parts: [] };
      batches.set(key, batch);
    }
    const geometry = object.geometry.index
      ? object.geometry.toNonIndexed()
      : object.geometry.clone();
    geometry.deleteAttribute('uv');
    geometry.applyMatrix4(object.matrixWorld);
    batch.parts.push(geometry);
    originals.add(object.geometry);
  });
  const merged = new THREE.Group();
  for (const batch of batches.values()) {
    const geometry = mergeGeometries(batch.parts);
    if (!geometry)
      throw new Error('Incompatible procedural mechanism geometry');
    const mesh = new THREE.Mesh(geometry, batch.material);
    mesh.name = batch.name;
    merged.add(mesh);
    batch.parts.forEach((part) => part.dispose());
  }
  originals.forEach((geometry) => geometry.dispose());
  return merged;
}

/** Constant wire diameter; reusable buffers deform with seat spacing and twist. */
export class MechanismSpring extends THREE.Mesh<
  THREE.BufferGeometry,
  THREE.Material
> {
  private readonly turns = appearance.mechanism.springTurns;
  private readonly segments = this.turns * 24;
  private readonly sides = 6;
  private previousStart = NaN;
  private previousEnd = NaN;
  private previousTwist = NaN;

  constructor(
    private readonly radius: number,
    private readonly wire: number,
    material: THREE.Material,
  ) {
    super(new THREE.BufferGeometry(), material);
    const count = (this.segments + 1) * this.sides;
    this.geometry.setAttribute(
      'position',
      new THREE.BufferAttribute(new Float32Array(count * 3), 3).setUsage(
        THREE.DynamicDrawUsage,
      ),
    );
    this.geometry.setAttribute(
      'normal',
      new THREE.BufferAttribute(new Float32Array(count * 3), 3).setUsage(
        THREE.DynamicDrawUsage,
      ),
    );
    const indices: number[] = [];
    for (let i = 0; i < this.segments; i++)
      for (let j = 0; j < this.sides; j++) {
        const a = i * this.sides + j,
          b = i * this.sides + ((j + 1) % this.sides);
        indices.push(a, b, a + this.sides, b, b + this.sides, a + this.sides);
      }
    this.geometry.setIndex(indices);
    // The containing CVT has fitted bounds; avoid recomputing bounds every frame.
    this.frustumCulled = false;
  }

  update(start: number, end: number, twist = 0): void {
    if (
      start === this.previousStart &&
      end === this.previousEnd &&
      twist === this.previousTwist
    )
      return;
    this.previousStart = start;
    this.previousEnd = end;
    this.previousTwist = twist;
    const position = this.geometry.getAttribute('position'),
      normal = this.geometry.getAttribute('normal');
    // Secondary opening has negative relative rotation and winds this spring.
    const sweep = -this.turns * Math.PI * 2 + twist;
    for (let i = 0; i <= this.segments; i++) {
      const t = i / this.segments,
        angle = sweep * t;
      const c = Math.cos(angle),
        s = Math.sin(angle);
      const pitch = (end - start) / (sweep * this.radius);
      const norm = Math.sqrt(1 + pitch * pitch);
      for (let j = 0; j < this.sides; j++) {
        const cross = (j * Math.PI * 2) / this.sides,
          a = Math.cos(cross),
          b = Math.sin(cross);
        const nx = a * c - (b * s * pitch) / norm,
          ny = a * s + (b * c * pitch) / norm,
          nz = -b / norm;
        const index = i * this.sides + j;
        position.setXYZ(
          index,
          this.radius * c + this.wire * nx,
          this.radius * s + this.wire * ny,
          start + t * (end - start) + this.wire * nz,
        );
        normal.setXYZ(index, nx, ny, nz);
      }
    }
    position.needsUpdate = true;
    normal.needsUpdate = true;
  }
}
