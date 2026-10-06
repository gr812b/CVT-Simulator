import { Group, Matrix4, Quaternion, Vector3 } from 'three';
import type { Model3DConfig } from '@utils/sceneTypes';

export type InspectionMount = 'primary' | 'secondary';

/** Presentation-only proper rotations. The mechanism's native coordinates and
 * all positionCVT transforms stay unchanged under this extra parent.
 * Primary: radial is up, positive axial is right, ramp plane faces the camera.
 * Secondary: shaft is vertical, roller 1 faces the camera at the starting pose.
 * The shared Y-up orbit controller therefore orbits the secondary shaft.
 */
export const inspectionBases: Record<InspectionMount, Parameters<Matrix4['set']>> = {
  primary: [0, 0, -1, 0, 1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 0, 1],
  secondary: [0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1],
};

export function orientInspectionModels(models: Model3DConfig[], mount: InspectionMount, initialHelixAngle = 0): Model3DConfig[] {
  const frame = new Group();
  frame.name = `${mount}-inspection-frame`;
  frame.quaternion.setFromRotationMatrix(new Matrix4().set(...inspectionBases[mount]));
  if (mount === 'secondary') {
    frame.quaternion.multiply(new Quaternion().setFromAxisAngle(new Vector3(0, 0, 1), -initialHelixAngle));
  }
  return [
    { id: 'inspectionFrame', object3D: frame },
    ...models.map(model => model.id === `${mount}Fixed` ? { ...model, parentId: 'inspectionFrame' } : model),
  ];
}
