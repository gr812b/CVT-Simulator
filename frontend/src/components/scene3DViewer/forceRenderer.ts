import { formatPreferredProjectedQuantity, normalizeUnitPreferences, type UnitPreferences } from '@utils/units';
import * as THREE from 'three';
import type { Scene3DController } from '@utils/Scene3DController';
import type { VisualReplaySample } from '@utils/reportReplay';
import type { ForcePlayback, ForceSample, ForceTrack } from './forceApi';
import { mechanismLayout, mechanismPose } from './mechanisms';
import { sceneDistance, type SceneGeometry } from './sceneSpec';
import { sceneAppearance } from '../../styles/theme';

export type ForceOptions = {
  body: ForceTrack['body'] | 'both';
  tracks: string[];
  components: string[];
  scale: number;
  labels: boolean;
};
const colors = sceneAppearance.forces;
const Z = new THREE.Vector3(0, 0, 1);
function showThroughHardware(arrow: THREE.ArrowHelper) {
  for (const object of [arrow.line, arrow.cone]) {
    const materials = Array.isArray(object.material)
      ? object.material
      : [object.material];
    materials.forEach((material) => {
      material.depthTest = false;
      material.depthWrite = false;
    });
    object.renderOrder = 20;
  }
}

export function forceBracket(
  data: Pick<ForcePlayback, 'times_s' | 'report_indices'>,
  sample: Pick<VisualReplaySample, 'simulationTime' | 'lowerIndex'>,
) {
  const times = data.times_s;
  let lo = 0,
    hi = data.report_indices.length - 1;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (data.report_indices[mid] <= sample.lowerIndex) lo = mid;
    else hi = mid - 1;
  }
  const lower = lo,
    upper = Math.min(times.length - 1, lower + 1);
  const duration = times[upper] - times[lower];
  return {
    lower,
    upper,
    alpha:
      duration > 0
        ? THREE.MathUtils.clamp(
            (sample.simulationTime - times[lower]) / duration,
            0,
            1,
          )
        : 0,
  };
}
export function forceAt(
  track: ForceTrack,
  bracket: ReturnType<typeof forceBracket>,
): ForceSample | null {
  const a = track.samples[bracket.lower],
    b = track.samples[bracket.upper];
  if (bracket.alpha === 0) return a ?? null;
  if (bracket.alpha === 1) return b ?? null;
  if (!a || !b) return null;
  const lerp = (x: number, y: number) =>
    THREE.MathUtils.lerp(x, y, bracket.alpha);
  return {
    components: a.components.map((v, i) =>
      lerp(v, b.components[i]),
    ) as ForceSample['components'],
    phase_rad: lerp(a.phase_rad ?? 0, b.phase_rad ?? 0),
    radius_m: lerp(a.radius_m ?? 0, b.radius_m ?? 0),
    axial_position_m: lerp(a.axial_position_m ?? 0, b.axial_position_m ?? 0),
  };
}

/** Scene-only coordinate transforms. Force magnitudes/decompositions are API data. */
export class ForceRenderer {
  private root = new THREE.Group();
  private arrows: Map<
    string,
    {
      group: THREE.Group;
      vectors: THREE.ArrowHelper[];
      arc: THREE.Line;
      tip: THREE.ArrowHelper;
      label: THREE.Sprite;
      text: string;
    }
  > = new Map();
  private forceScale: number;
  private torqueScale: number;
  constructor(
    private controller: Scene3DController,
    private geometry: SceneGeometry,
    private data: ForcePlayback,
  ) {
    const max = (unit: string) => {
      let peak = 1;
      for (const track of data.tracks) {
        if (track.unit !== unit) continue;
        for (const sample of track.samples) {
          if (sample) peak = Math.max(peak, Math.hypot(...sample.components));
        }
      }
      return peak;
    };
    this.forceScale = (geometry.primaryMaxRadius * 0.85) / max('N');
    this.torqueScale = 1 / max('N·m');
    for (const track of data.tracks) {
      const group = new THREE.Group();
      const vectors = [
        colors.resultant,
        colors.axial,
        colors.radial,
        colors.tangential,
      ].map(
        (color) =>
          new THREE.ArrowHelper(Z, new THREE.Vector3(), 1, color, 0.15, 0.08),
      );
      vectors.forEach((arrow) => {
        group.add(arrow);
        showThroughHardware(arrow);
      });
      const arc = new THREE.Line(
        new THREE.BufferGeometry().setAttribute(
          'position',
          new THREE.BufferAttribute(new Float32Array(48 * 3), 3),
        ),
        new THREE.LineBasicMaterial({ color: colors.torque, depthTest: false }),
      );
      const tip = new THREE.ArrowHelper(
        Z,
        new THREE.Vector3(),
        0.15,
        colors.torque,
        0.15,
        0.1,
      );
      showThroughHardware(tip);
      group.add(arc, tip);
      const label = new THREE.Sprite(
        new THREE.SpriteMaterial({ transparent: true, depthTest: false }),
      );
      label.scale.set(2.5, 0.55, 1);
      group.add(label);
      group.renderOrder = 20;
      this.root.add(group);
      this.arrows.set(track.key, { group, vectors, arc, tip, label, text: '' });
    }
    controller.getScene().add(this.root);
  }
  update(sample: VisualReplaySample, shift: number, options: ForceOptions, preferences?: UnitPreferences) {
    const units = normalizeUnitPreferences(preferences);
    const bracket = forceBracket(this.data, sample);
    const l = mechanismLayout(this.geometry),
      pose = mechanismPose(this.geometry, shift);
    for (const track of this.data.tracks) {
      const item = this.arrows.get(track.key)!;
      const s = forceAt(track, bracket);
      item.group.visible =
        (options.body === 'both' || options.body === track.body) &&
        options.tracks.includes(track.key) &&
        !!s;
      if (!s || !item.group.visible) continue;
      const primary = track.body === 'primary';
      const fixed = this.controller.getModel(
        primary ? 'primaryFixed' : 'secondaryFixed',
      )?.object3D;
      const moving = this.controller.getModel(
        primary ? 'primaryMoving' : 'secondaryMoving',
      )?.object3D;
      if (!fixed || !moving) {
        item.group.visible = false;
        continue;
      }
      fixed.updateWorldMatrix(true, false);
      const center = fixed.getWorldPosition(new THREE.Vector3());
      const movingCenter = moving.getWorldPosition(new THREE.Vector3());
      const rotation = new THREE.Euler().setFromQuaternion(
        (track.anchor === 'helix' ? moving : fixed).getWorldQuaternion(
          new THREE.Quaternion(),
        ),
      ).z;
      const phase =
        (s.phase_rad ?? 0) + (track.anchor === 'belt' ? 0 : rotation);
      const radial = new THREE.Vector3(Math.cos(phase), Math.sin(phase), 0);
      const tangent = new THREE.Vector3(-Math.sin(phase), Math.cos(phase), 0);
      const axial = new THREE.Vector3(0, 0, primary ? -1 : 1);
      let radius = sceneDistance(s.radius_m ?? 0),
        z = movingCenter.z;
      if (track.anchor === 'ramp')
        z = center.z + l.back - sceneDistance(s.axial_position_m ?? 0);
      if (track.anchor === 'helix')
        z =
          center.z +
          l.rollerZ +
          sceneDistance(pose?.secondary_axial_position_m ?? 0);
      if (track.anchor === 'spring')
        z =
          center.z +
          (primary
            ? l.capP - sceneDistance(pose?.primary_ramp_shift_m ?? 0)
            : l.capS + sceneDistance(pose?.secondary_axial_position_m ?? 0));
      if (track.anchor === 'belt') {
        const beltZ = -Math.max(this.geometry.deadzoneShift, shift) / 2;
        z =
          beltZ +
          (primary ? 1 : -1) *
            (this.geometry.beltOuterWidth / 2 -
              this.geometry.cordDepth * Math.tan(this.geometry.halfAngle));
      }
      if (track.unit === 'N·m') {
        radius =
          (primary
            ? this.geometry.primaryMaxRadius
            : this.geometry.secondaryMaxRadius) * 0.55;
        z += primary ? 0.5 : -0.5;
      }
      const origin = new THREE.Vector3(center.x, center.y, z).addScaledVector(
        radial,
        track.unit === 'N·m' ? 0 : radius,
      );
      item.group.position.copy(origin);
      const parts = [
        axial.clone().multiplyScalar(s.components[0]),
        radial.clone().multiplyScalar(s.components[1]),
        tangent.clone().multiplyScalar(s.components[2]),
      ];
      const force = parts[0].clone().add(parts[1]).add(parts[2]);
      const all = [force, ...parts];
      const scale = this.forceScale * options.scale;
      item.vectors.forEach((arrow, index) => {
        const vector = all[index],
          length = vector.length() * scale;
        arrow.visible =
          track.unit === 'N' &&
          length > 1e-7 &&
          (index === 0 ||
            options.components.includes(
              ['', 'axial', 'radial', 'tangential'][index],
            ));
        if (arrow.visible) {
          arrow.setDirection(vector.clone().normalize());
          arrow.setLength(
            length,
            Math.min(0.25, length * 0.22),
            Math.min(index ? 0.07 : 0.12, length * 0.12),
          );
        }
      });
      item.arc.visible = item.tip.visible =
        track.unit === 'N·m' && Math.abs(s.components[0]) > 1e-8;
      if (item.arc.visible) {
        const angle =
          Math.sign(s.components[0]) *
          Math.min(
            1.8 * Math.PI,
            Math.abs(s.components[0]) *
              this.torqueScale *
              options.scale *
              1.8 *
              Math.PI,
          );
        const positions = item.arc.geometry.getAttribute('position');
        for (let i = 0; i < 48; i++) {
          const theta = phase + (angle * i) / 47;
          positions.setXYZ(
            i,
            radius * Math.cos(theta),
            radius * Math.sin(theta),
            0,
          );
        }
        positions.needsUpdate = true;
        item.arc.geometry.computeBoundingSphere();
        item.tip.position.set(
          radius * Math.cos(phase + angle),
          radius * Math.sin(phase + angle),
          0,
        );
        item.tip.setDirection(
          new THREE.Vector3(
            -Math.sin(phase + angle),
            Math.cos(phase + angle),
            0,
          ).multiplyScalar(Math.sign(angle)),
        );
      }
      item.label.visible = options.labels;
      if (options.labels) {
        const text = `${track.label}: ${formatPreferredProjectedQuantity(track.unit === 'N' ? force.length() : s.components[0], '', track.unit, 'output', units, 2)}`;
        if (text !== item.text) {
          const canvas = document.createElement('canvas');
          canvas.width = 512;
          canvas.height = 96;
          const ctx = canvas.getContext('2d')!;
          ctx.fillStyle = '#101722e8';
          ctx.fillRect(0, 0, 512, 96);
          ctx.fillStyle = '#fff';
          ctx.font = '24px sans-serif';
          ctx.fillText(text, 12, 58);
          item.label.material.map?.dispose();
          item.label.material.map = new THREE.CanvasTexture(canvas);
          item.label.material.needsUpdate = true;
          item.text = text;
        }
        item.label.position
          .copy(force)
          .multiplyScalar(track.unit === 'N' ? scale : 0)
          .add(new THREE.Vector3(0, 0.4, 0));
      }
    }
  }
  dispose() {
    this.root.removeFromParent();
    this.root.traverse((object) => {
      if (
        object instanceof THREE.Mesh ||
        object instanceof THREE.Line ||
        object instanceof THREE.Sprite
      ) {
        if ('geometry' in object) object.geometry.dispose();
        const materials = Array.isArray(object.material)
          ? object.material
          : [object.material];
        for (const material of materials) {
          if ('map' in material)
            (material.map as THREE.Texture | null)?.dispose();
          material.dispose();
        }
      }
    });
  }
}
