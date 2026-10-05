import * as THREE from 'three';
import { sceneAppearance } from '../../styles/theme';
import type { NumericRange, SpatialDomainSample } from '@utils/spatialFields';
import type { SceneGeometry } from './sceneSpec';
import { sceneDistance } from './sceneSpec';

const PRIMARY_WRAP_REGION = 'primary_wrap';
const SECONDARY_WRAP_REGION = 'secondary_wrap';

export interface BeltSceneLayout {
  primaryCenter: [number, number];
  secondaryCenter: [number, number];
}

interface Point2 {
  x: number;
  y: number;
}

function circleCenter(a: Point2, b: Point2, c: Point2): Point2 | null {
  const determinant =
    2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y));
  if (Math.abs(determinant) < 1e-14) return null;

  const a2 = a.x * a.x + a.y * a.y;
  const b2 = b.x * b.x + b.y * b.y;
  const c2 = c.x * c.x + c.y * c.y;
  return {
    x: (a2 * (b.y - c.y) + b2 * (c.y - a.y) + c2 * (a.y - b.y)) / determinant,
    y: (a2 * (c.x - b.x) + b2 * (a.x - c.x) + c2 * (b.x - a.x)) / determinant,
  };
}

function regionCircleCenter(
  sample: Pick<SpatialDomainSample, 'position' | 'regionKeys'>,
  regionKey: string,
): Point2 | null {
  const points = sample.position
    .filter((_, index) => sample.regionKeys[index] === regionKey)
    .map(([x, y]) => ({ x, y }));
  if (points.length < 3) return null;
  return circleCenter(
    points[0],
    points[Math.floor(points.length / 2)],
    points[points.length - 1],
  );
}

function boundsCenter(
  sample: Pick<SpatialDomainSample, 'position' | 'regionKeys'>,
): Point2 {
  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  sample.position.forEach(([x, y]) => {
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  });
  return { x: (minX + maxX) / 2, y: (minY + maxY) / 2 };
}

function scenePath(
  sample: Pick<SpatialDomainSample, 'position' | 'regionKeys'>,
  axialPosition: number,
): {
  points: THREE.Vector3[];
  layout: BeltSceneLayout | null;
} {
  const primary = regionCircleCenter(sample, PRIMARY_WRAP_REGION);
  const secondary = regionCircleCenter(sample, SECONDARY_WRAP_REGION);
  const origin =
    primary !== null && secondary !== null
      ? { x: (primary.x + secondary.x) / 2, y: (primary.y + secondary.y) / 2 }
      : boundsCenter(sample);

  const transform = (point: Point2): [number, number] => [
    sceneDistance(point.x - origin.x),
    sceneDistance(point.y - origin.y),
  ];
  const points = sample.position.map(([x, y]) => {
    const [sceneX, sceneY] = transform({ x, y });
    return new THREE.Vector3(sceneX, sceneY, axialPosition);
  });

  if (primary === null || secondary === null) return { points, layout: null };
  return {
    points,
    layout: {
      primaryCenter: transform(primary),
      secondaryCenter: transform(secondary),
    },
  };
}

/** Return path-derived pulley centers without reconstructing belt mechanics. */
export function beltSceneLayout(
  sample: Pick<SpatialDomainSample, 'position' | 'regionKeys'>,
): BeltSceneLayout | null {
  return scenePath(sample, 0).layout;
}

function tensionColor(value: number, range: NumericRange): THREE.Color {
  const span = range.maximum - range.minimum;
  const normalized =
    span > 0 ? Math.min(1, Math.max(0, (value - range.minimum) / span)) : 0.5;
  return new THREE.Color().setHSL(((1 - normalized) * 2) / 3, 0.9, 0.5);
}

function createGeometry(
  path: THREE.Vector3[],
  geometry: SceneGeometry,
  tensionValues: readonly number[] | undefined,
  tensionRange: NumericRange | null,
  tensionEnabled: boolean,
  existing: THREE.BufferGeometry,
): THREE.BufferGeometry {
  if (path.length < 4) return new THREE.BufferGeometry();

  const ringSize = 4;
  const length = path.length * ringSize * 3;
  const reuse = existing.getAttribute('position')?.array.length === length;
  const positions = reuse ? existing.getAttribute('position').array as Float32Array : new Float32Array(length);
  const colors = reuse ? existing.getAttribute('color').array as Float32Array : new Float32Array(length);
  const indices: number[] = [];
  const neutral = new THREE.Color(sceneAppearance.belt);
  const unavailable = new THREE.Color(sceneAppearance.unavailable);

  for (let index = 0; index < path.length; index += 1) {
    const previous = path[(index - 1 + path.length) % path.length];
    const current = path[index];
    const next = path[(index + 1) % path.length];
    const tangentX = next.x - previous.x;
    const tangentY = next.y - previous.y;
    const tangentLength = Math.hypot(tangentX, tangentY);

    // CINDER belt.path is ordered counter-clockwise around the loop, so the
    // left-hand path normal points inward toward the pulley centres. A rubber
    // V-belt is narrower on that inner/radial face and wider on its outer face.
    const inwardNormalX = tangentLength > 0 ? -tangentY / tangentLength : 0;
    const inwardNormalY = tangentLength > 0 ? tangentX / tangentLength : 1;
    const outerRadial = -geometry.cordDepth;
    const innerRadial = geometry.beltHeight * 0.86 - geometry.cordDepth;

    // Four corners of the physical trapezoidal section, viewed along belt
    // travel: wide outer face first, then the narrow inner face.
    const radialOffsets = [outerRadial, outerRadial, innerRadial, innerRadial];
    const axialOffsets = [
      -geometry.beltOuterWidth / 2,
      geometry.beltOuterWidth / 2,
      geometry.beltInnerWidth / 2,
      -geometry.beltInnerWidth / 2,
    ];

    const value = tensionValues?.[index];
    const color = !tensionEnabled
      ? neutral
      : typeof value === 'number' &&
        Number.isFinite(value) &&
        tensionRange !== null
        ? tensionColor(value, tensionRange)
        : unavailable;

    for (let corner = 0; corner < ringSize; corner += 1) {
      const vertex = (index * ringSize + corner) * 3;
      positions[vertex] = current.x + inwardNormalX * radialOffsets[corner];
      positions[vertex + 1] = current.y + inwardNormalY * radialOffsets[corner];
      positions[vertex + 2] = current.z + axialOffsets[corner];
      colors[vertex] = color.r;
      colors[vertex + 1] = color.g;
      colors[vertex + 2] = color.b;
    }
  }

  if (!reuse) for (let index = 0; index < path.length; index += 1) {
    const next = (index + 1) % path.length;
    for (let corner = 0; corner < ringSize; corner += 1) {
      const nextCorner = (corner + 1) % ringSize;
      const a = index * ringSize + corner;
      const b = index * ringSize + nextCorner;
      const c = next * ringSize + nextCorner;
      const d = next * ringSize + corner;
      indices.push(a, b, c, a, c, d);
    }
  }

  const result = existing;
  if (!reuse) {
    result.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    result.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    result.setIndex(indices);
  } else {
    result.getAttribute('position').needsUpdate = true;
    result.getAttribute('color').needsUpdate = true;
  }
  result.computeVertexNormals();
  result.computeBoundingSphere();
  return result;
}

export function createBeltMesh(): THREE.Mesh {
  const mesh = new THREE.Mesh(
    new THREE.BufferGeometry(),
    new THREE.MeshPhysicalMaterial({
      color: 0xffffff,
      vertexColors: true,
      metalness: 0.05,
      roughness: 0.8,
      clearcoat: 0.1,
      clearcoatRoughness: 0.8,
      flatShading: true,
      side: THREE.DoubleSide,
    }),
  );
  const teeth = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshStandardMaterial({ color: sceneAppearance.belt, roughness: 0.85 }), 96);
  teeth.name = 'belt-cogs';
  teeth.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  teeth.frustumCulled = false;
  mesh.add(teeth);
  return mesh;
}

/** Replace the displayed belt directly from one CINDER belt.path sample. */
export function updateBeltMesh(
  mesh: THREE.Mesh,
  sample: Pick<SpatialDomainSample, 'position' | 'regionKeys'>,
  geometry: SceneGeometry,
  axialPosition: number,
  tensionValues: readonly number[] | undefined,
  tensionRange: NumericRange | null,
  tensionEnabled: boolean,
  travel = 0,
): BeltSceneLayout | null {
  const { points, layout } = scenePath(sample, axialPosition);
  const nextGeometry = createGeometry(
    points,
    geometry,
    tensionValues,
    tensionRange,
    tensionEnabled,
    mesh.geometry,
  );
  mesh.geometry = nextGeometry;
  updateCogs(mesh, points, geometry, travel, tensionEnabled);
  return layout;
}

/** Schematic cog spacing; motion follows integrated belt transport, including slip. */
function updateCogs(mesh: THREE.Mesh, path: THREE.Vector3[], geometry: SceneGeometry, travel: number, tension: boolean) {
  const teeth = mesh.getObjectByName('belt-cogs') as THREE.InstancedMesh | undefined;
  if (!teeth || path.length < 4) return;
  teeth.visible = !tension;
  if (tension) return;
  const cumulative = [0];
  for (let i = 0; i < path.length; i++) cumulative.push(cumulative[i] + path[i].distanceTo(path[(i + 1) % path.length]));
  const length = cumulative.at(-1)!;
  if (length <= 0) return;
  const pitch = length / teeth.count;
  const matrix = new THREE.Matrix4(), tangent = new THREE.Vector3(), inward = new THREE.Vector3(), z = new THREE.Vector3(0, 0, 1);
  const position = new THREE.Vector3(), scale = new THREE.Vector3(pitch * 0.6, geometry.beltHeight * 0.14, geometry.beltInnerWidth);
  for (let i = 0; i < teeth.count; i++) {
    const distance = ((i * pitch + travel) % length + length) % length;
    let lo = 0, hi = path.length;
    while (lo + 1 < hi) { const mid = (lo + hi) >> 1; if (cumulative[mid] <= distance) lo = mid; else hi = mid; }
    const next = (lo + 1) % path.length;
    tangent.copy(path[next]).sub(path[lo]).normalize();
    inward.set(-tangent.y, tangent.x, 0);
    position.copy(path[lo]).lerp(path[next], (distance - cumulative[lo]) / (cumulative[lo + 1] - cumulative[lo]));
    position.addScaledVector(inward, geometry.beltHeight * 0.93 - geometry.cordDepth);
    matrix.makeBasis(tangent, inward, z).scale(scale).setPosition(position);
    teeth.setMatrixAt(i, matrix);
  }
  teeth.instanceMatrix.needsUpdate = true;
}
