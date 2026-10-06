import { useEffect, useRef } from 'react';
import { Quaternion, Vector3 } from 'three';
import type { Scene3DController } from '@utils/Scene3DController';
import { mechanismLayout, mechanismPose } from './mechanisms';
import { sceneDistance, type SceneGeometry } from './sceneSpec';
import type { InspectionMount } from './inspectionFrame';

/** Camera-following orientation and named reference points, outside WebGL.
 * This overlay never captures orbit, pan, pinch, wheel or pointer events.
 */
export function InspectionOverlay({ controller, mount, geometry, shift }: {
  controller: Scene3DController;
  mount: InspectionMount;
  geometry: SceneGeometry;
  shift: number;
}) {
  const corner = useRef<SVGSVGElement>(null);
  const labels = useRef<SVGSVGElement>(null);
  useEffect(() => {
    const axes = corner.current;
    const markers = labels.current;
    if (!axes || !markers) return;
    const vector = new Vector3();
    const worldRotation = new Quaternion();
    const cameraRotation = new Quaternion();
    const primary = mount === 'primary';
    const definitions = [
      { key: 'axial', label: 'Axial', direction: new Vector3(0, 0, primary ? -1 : 1) },
      { key: 'radial', label: primary ? 'Radial' : 'Radial 1', direction: new Vector3(1, 0, 0) },
      { key: 'third', label: primary ? 'Across' : 'Tangent 1', direction: new Vector3(0, 1, 0) },
    ];
    const layout = mechanismLayout(geometry);
    const update = () => {
      const camera = controller.getCamera();
      camera.updateMatrixWorld();
      camera.getWorldQuaternion(cameraRotation).invert();
      // SecondaryMoving includes the actual relative twist of roller 1.
      const reference = controller.getModel(primary ? 'primaryFixed' : 'secondaryMoving')?.object3D;
      if (!reference) return;
      reference.updateWorldMatrix(true, false);
      reference.getWorldQuaternion(worldRotation);
      for (const axis of definitions) {
        const group = axes.querySelector<SVGGElement>(`[data-axis="${axis.key}"]`)!;
        vector.copy(axis.direction).applyQuaternion(worldRotation).applyQuaternion(cameraRotation);
        const x = 64 + vector.x * 30, y = 59 - vector.y * 30;
        const foreshortened = Math.hypot(vector.x, vector.y) < 0.12;
        const line = group.querySelector('line')!;
        line.setAttribute('x2', String(x)); line.setAttribute('y2', String(y));
        const dot = group.querySelector('circle')!;
        dot.setAttribute('cx', String(x)); dot.setAttribute('cy', String(y));
        dot.setAttribute('r', foreshortened ? '3.5' : '2');
        const text = group.querySelector('text')!;
        text.setAttribute('x', String(x + (foreshortened ? 10 : vector.x < -0.2 ? -5 : 5)));
        text.setAttribute('y', String(y + (foreshortened ? 15 : vector.y > 0.2 ? -6 : 12)));
        text.setAttribute('text-anchor', !foreshortened && vector.x < -0.2 ? 'end' : 'start');
        text.textContent = axis.label + (foreshortened ? vector.z > 0 ? ' ⊙' : ' ⊗' : '');
        group.style.opacity = String(vector.z < -0.1 ? 0.6 : 1);
      }
      const rect = markers.getBoundingClientRect();
      const mark = (key: string, local: Vector3 | null) => {
        const group = markers.querySelector<SVGGElement>(`[data-marker="${key}"]`)!;
        if (!local) { group.style.display = 'none'; return; }
        const point = local.applyMatrix4(reference.matrixWorld).project(camera);
        const visible = point.z >= -1 && point.z <= 1 && Math.abs(point.x) <= 1 && Math.abs(point.y) <= 1;
        group.style.display = visible ? '' : 'none';
        if (visible) group.setAttribute('transform', `translate(${(point.x + 1) * rect.width / 2},${(1 - point.y) * rect.height / 2})`);
      };
      if (primary) {
        const spec = geometry.mechanisms?.primary;
        const tip = spec?.ramp_points_m[0];
        const pose = mechanismPose(geometry, shift);
        mark('pivot', spec ? new Vector3(sceneDistance(spec.pivot_m[1]), 0, layout.pivotZ) : null);
        mark('tip', tip && pose ? new Vector3(sceneDistance(tip[1]), 0,
          layout.back - sceneDistance(tip[0] + pose.primary_ramp_shift_m)) : null);
        mark('roller', null);
      } else {
        mark('pivot', null); mark('tip', null);
        mark('roller', new Vector3(layout.helixR, 0, layout.rollerZ - layout.s0));
      }
    };
    update();
    const unsubscribe = controller.onFrame(update);
    return unsubscribe;
  }, [controller, mount, geometry, shift]);
  const overlayStyle = { position: 'absolute', pointerEvents: 'none', zIndex: 2, color: 'var(--mantine-color-text)' } as const;
  return <>
    <svg ref={labels} style={{ ...overlayStyle, inset: 0, width: '100%', height: '100%', overflow: 'hidden' }} aria-label="Mechanism reference points" role="img">
      <title>{mount === 'primary' ? 'Fixed pivot and ramp starting tip at the current closure' : 'Reference roller 1'}</title>
      {(['pivot', 'tip', 'roller'] as const).map(key => <g key={key} data-marker={key} style={{ display: 'none' }}>
        <circle r={4} fill="var(--mantine-color-body)" stroke="currentColor" strokeWidth={1.5}/>
        <path d={key === 'pivot' ? 'M-3 3 L-10 15 H-16' : 'M3 -3 L10 -15 H16'} fill="none" stroke="currentColor"/>
        <text x={key === 'pivot' ? -19 : 19} y={key === 'pivot' ? 19 : -12} textAnchor={key === 'pivot' ? 'end' : 'start'}
          fontSize={11} fill="currentColor" stroke="var(--mantine-color-body)" strokeWidth={3} paintOrder="stroke">
          {key === 'pivot' ? 'Pivot' : key === 'tip' ? 'Ramp start' : 'Roller 1'}
        </text>
      </g>)}
    </svg>
    <svg ref={corner} viewBox="0 0 156 112" role="img" aria-label={`${mount} camera-following orientation axes`}
      style={{ ...overlayStyle, left: 8, bottom: 8, width: 156, height: 112, borderRadius: 6, background: 'var(--mantine-color-body)' }}>
      <title>{mount === 'primary' ? 'Axial and radial directions; across is normal to the ramp plane' : 'Axial is along the shaft; radial and tangent follow roller 1'}. A circled dot points toward you; a circled cross points away.</title>
      <text x={8} y={14} fill="currentColor" fontSize={9} opacity={0.7}>{mount === 'primary' ? 'Ramp frame' : 'Roller 1 frame'}</text>
      {['axial', 'radial', 'third'].map(key => <g key={key} data-axis={key}>
        <line x1={64} y1={59} x2={64} y2={59} stroke="currentColor" strokeWidth={1.5}/>
        <circle cx={64} cy={59} r={2} fill="currentColor"/>
        <text fontSize={10} fill="currentColor"/>
      </g>)}
      <circle cx={64} cy={59} r={2} fill="currentColor"/>
    </svg>
  </>;
}
