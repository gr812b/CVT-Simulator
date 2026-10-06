import * as THREE from 'three';
import type { Model3DConfig } from '@utils/sceneTypes';
import type { Scene3DController } from '@utils/Scene3DController';
import { sceneAppearance as appearance } from '../../styles/theme';
import { sceneDistance, type SceneGeometry } from './sceneSpec';
import {
  beam,
  batchRigidParts,
  cylinder,
  MechanismSpring,
  metal,
  positionBeam,
  profileSolid,
  rampBackingRadius,
  rampSolid,
  ring,
  slottedSleeve,
} from './mechanismGeometry';

const visual = appearance.mechanism;
const v = (r: number, z: number, across = 0) => new THREE.Vector3(r, across, z);
const layouts = new WeakMap<SceneGeometry, ReturnType<typeof resolveLayout>>();

export function sheaveHub(minimum: number, geometry: SceneGeometry): number {
  return Math.max(minimum - geometry.beltHeight, minimum * 0.14);
}

/** Illustrative tip collars: 150 g per flyweight is the length reference.
 * Both cylinders grow equally outwards from fixed inner faces, leaving the
 * roller/arm lane clear. Their common axis, radius and combined centre stay
 * fixed; each cylinder's material length is exactly proportional to tip mass.
 * Recorded scenes without an identified tip mass retain the original drawing.
 */
export function primaryTipDimensions(
  rollerRadius: number,
  tipMassPerFlyweightKg?: number | null,
) {
  const legacyLength = rollerRadius * 0.45;
  const legacyCentre = rollerRadius * 1.15 * 0.85;
  const identified = tipMassPerFlyweightKg != null &&
    Number.isFinite(tipMassPerFlyweightKg) && tipMassPerFlyweightKg >= 0;
  const length = identified
    ? rollerRadius * 0.8 * (tipMassPerFlyweightKg / 0.15)
    : legacyLength;
  return {
    radius: rollerRadius * 1.25,
    length,
    centreAcross: identified
      ? legacyCentre - legacyLength / 2 + length / 2
      : legacyCentre,
  };
}

export function mechanismPose(geometry: SceneGeometry, shift: number) {
  const poses = geometry.mechanisms?.poses;
  if (!poses?.length) return null;
  const index = poses.findIndex((p) => sceneDistance(p.shift_m) >= shift);
  if (index <= 0) return index < 0 ? poses.at(-1)! : poses[0];
  const a = poses[index - 1],
    b = poses[index];
  const alpha =
    (shift - sceneDistance(a.shift_m)) / sceneDistance(b.shift_m - a.shift_m);
  const lerp = (x: number, y: number) => THREE.MathUtils.lerp(x, y, alpha);
  return {
    ...a,
    primary_ramp_shift_m: lerp(a.primary_ramp_shift_m, b.primary_ramp_shift_m),
    secondary_axial_position_m: lerp(
      a.secondary_axial_position_m,
      b.secondary_axial_position_m,
    ),
    secondary_angle_rad: lerp(a.secondary_angle_rad, b.secondary_angle_rad),
    primary_roller_m:
      a.primary_roller_m && b.primary_roller_m
        ? [
            lerp(a.primary_roller_m[0], b.primary_roller_m[0]),
            lerp(a.primary_roller_m[1], b.primary_roller_m[1]),
          ]
        : null,
  };
}

/** Only packaging lives here. Contact positions and relative motion come from CINDER. */
function resolveLayout(g: SceneGeometry) {
  const spec = g.mechanisms,
    slope = Math.tan(g.halfAngle);
  const clearance = g.beltHeight * visual.clearance,
    wall = g.beltHeight * visual.wall;
  const hubP = sheaveHub(g.primaryMinRadius, g),
    hubS = sheaveHub(g.secondaryMinRadius, g);
  const p0 =
    g.beltOuterWidth -
    2 * (g.primaryMinRadius - hubP) * slope +
    g.deadzoneShift;
  const s0 = -g.beltOuterWidth + 2 * (g.secondaryMaxRadius - hubS) * slope;
  const backFace = (maximum: number, hub: number) => {
    const rim = maximum + g.beltHeight * 0.12;
    return Math.max((rim - hub) * slope + rim * 0.055, rim * 0.055 * 2.25);
  };
  const pTravel = spec?.poses.map((p) =>
    sceneDistance(p.primary_ramp_shift_m),
  ) ?? [0, g.maxShift];
  const sTravel = spec?.poses.map((p) =>
    sceneDistance(p.secondary_axial_position_m),
  ) ?? [0];
  const primary = spec?.primary;
  const rollerP = primary ? sceneDistance(primary.roller_radius_m) : wall;
  const rampAxial = primary?.ramp_points_m.map((p) => sceneDistance(p[0])) ?? [
    0,
  ];
  const back =
    p0 +
    backFace(g.primaryMaxRadius, hubP) +
    Math.max(...rampAxial) +
    2 * clearance;
  const pivotZ = back - sceneDistance(primary?.pivot_m[0] ?? 0);
  const helixR = spec?.secondary_helix_points_m.length
    ? sceneDistance(
        Math.hypot(
          spec.secondary_helix_points_m[0][0],
          spec.secondary_helix_points_m[0][1],
        ),
      )
    : hubS;
  const shaftP = hubP * 0.52,
    shaftS = Math.min(hubS * 0.52, helixR * 0.55);
  const guideR = shaftP + wall * 1.8;
  const springP = guideR + wall * 2;
  const fixedSeatP = p0 + backFace(g.primaryMaxRadius, hubP) + clearance;
  const wire = g.beltHeight * visual.springWire;
  const capP = Math.max(
    pivotZ - rollerP * 1.7,
    fixedSeatP + Math.max(...pTravel) + (visual.springTurns * 2 + 4) * wire,
  );
  const carrierP = Math.max(pivotZ + rollerP, capP + clearance + wall);
  const guideRoller = g.beltHeight * visual.guideRoller;
  // The guide pins also support the fixed spring seat outside the moving sleeve.
  const pinP = fixedSeatP - wall / 2;
  const pathP = [Math.min(...pTravel), Math.max(...pTravel)].map(
    (x) => new THREE.Vector2(0, pinP - p0 + x),
  );
  const trackSpacing = Math.min(
    ...(spec?.poses.slice(1).flatMap((pose, i) => {
      const previous = spec.poses[i];
      const dz = sceneDistance(
        pose.secondary_axial_position_m - previous.secondary_axial_position_m,
      );
      if (Math.abs(dz) < 1e-10) return [];
      const slope =
        (helixR * (pose.secondary_angle_rad - previous.secondary_angle_rad)) /
        dz;
      return [
        (Math.PI * 2 * helixR) / visual.trackCount / Math.hypot(1, slope),
      ];
    }) ?? []),
  );
  const rollerS = Math.min(
    g.beltHeight * visual.secondaryRoller,
    helixR * 0.12,
    trackSpacing * 0.3,
  );
  const rollerZ =
    s0 +
    Math.min(...sTravel) -
    backFace(g.secondaryMaxRadius, hubS) -
    2 * (rollerS + clearance);
  const pathS =
    spec?.poses
      .map(
        (p) =>
          new THREE.Vector2(
            helixR * p.secondary_angle_rad,
            rollerZ + sceneDistance(p.secondary_axial_position_m),
          ),
      )
      .filter(
        (point, index, points) =>
          index === 0 || point.distanceToSquared(points[index - 1]) > 1e-14,
      ) ?? [];
  const capS = rollerZ - rollerS - clearance;
  const springWindings =
    visual.springTurns +
    Math.max(
      0,
      ...(spec?.poses.map((p) => -p.secondary_angle_rad / (Math.PI * 2)) ?? []),
    );
  const baseS =
    capS + Math.min(...sTravel) - wall - (springWindings * 2 + 4) * wire;
  const sleeveTop = rollerZ + Math.max(...sTravel) + rollerS + clearance;
  return {
    clearance,
    wall,
    p0,
    s0,
    back,
    pivotZ,
    shaftP,
    shaftS,
    guideR,
    guideRoller,
    springP,
    fixedSeatP,
    capP,
    carrierP,
    pinP,
    pathP,
    helixR,
    rollerS,
    rollerZ,
    pathS,
    capS,
    baseS,
    sleeveTop,
    wire,
    pTravel,
    sTravel,
  };
}

export function mechanismLayout(g: SceneGeometry) {
  let value = layouts.get(g);
  if (!value) {
    value = resolveLayout(g);
    layouts.set(g, value);
  }
  return value;
}

function copies(
  geometry: THREE.BufferGeometry,
  material: THREE.Material,
  count: number = visual.trackCount,
): THREE.Group {
  const group = new THREE.Group();
  for (let i = 0; i < count; i++) {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = 'slot-wall';
    mesh.rotation.z = (i * Math.PI * 2) / count;
    group.add(mesh);
  }
  return group;
}

function radialRollers(
  radius: number,
  z: number,
  rollerRadius: number,
  wall: number,
  hub: number,
  color: string,
): THREE.Group {
  const group = new THREE.Group(),
    pinMaterial = metal(color),
    rollerMaterial = metal(color);
  for (let i = 0; i < visual.trackCount; i++) {
    const station = new THREE.Group();
    station.rotation.z = (i * Math.PI * 2) / visual.trackCount;
    const pin = cylinder(rollerRadius * 0.34, radius + wall - hub, pinMaterial);
    pin.rotation.y = Math.PI / 2;
    pin.position.copy(v((hub + radius + wall) / 2, z));
    const roller = cylinder(rollerRadius, wall * 1.6, rollerMaterial);
    roller.rotation.y = Math.PI / 2;
    roller.position.copy(v(radius, z));
    station.add(pin, roller);
    group.add(station);
  }
  return group;
}

export function createMechanisms(g: SceneGeometry, focus?: 'primary' | 'secondary'): Model3DConfig[] {
  const spec = g.mechanisms;
  if (!spec) return [];
  const l = mechanismLayout(g),
    models: Model3DConfig[] = [];
  const fixed = metal(appearance.fixedSheave),
    moving = metal(appearance.movingSheave);
  if (spec.primary && focus !== 'secondary') {
    const p = spec.primary,
      radius = sceneDistance(p.roller_radius_m),
      width = radius * 1.15;
    const tipDimensions = primaryTipDimensions(radius, p.tip_mass_per_flyweight_kg);
    const armThickness = radius * 0.26,
      lugThickness = radius * 0.32,
      lugRadius = radius * 0.58;
    // Fixed cheeks sit outside the moving arm plates, with a visible clearance.
    const lugAcross = width * 0.68 + armThickness / 2 + l.clearance * 0.35 + lugThickness / 2;
    const carrierZ = l.carrierP - l.wall / 2;
    const pivot = v(sceneDistance(p.pivot_m[1]), l.pivotZ);
    const carrier = new THREE.Group(),
      weights = new THREE.Group(),
      ramps = new THREE.Group();
    if (!focus) carrier.add(
      ring(
        l.shaftP * 0.92,
        l.shaftP + l.wall,
        carrierZ - l.wall * 0.8,
        carrierZ + l.wall * 0.8,
        fixed,
      ),
    );
    const rampPoints = p.ramp_points_m.map(
      ([axial, radial]) =>
        new THREE.Vector2(
          sceneDistance(radial),
          l.back - sceneDistance(axial) - l.p0,
        ),
    );
    const rampDepth = l.wall * 1.8;
    const rampGeometry = rampSolid(
      rampPoints,
      p.roller_side_sign,
      rampDepth,
      width,
    );
    const heel = rampBackingRadius(rampPoints, p.roller_side_sign, rampDepth);
    const backingSide = Math.sign(heel - rampPoints[0].x);
    const rampMaterial = metal(appearance.movingSheave),
      weightMaterial = metal(appearance.fixedSheave),
      rollerMaterial = metal(appearance.shaft);
    for (let i = 0; i < (focus ? 1 : p.count); i++) {
      const angle = (i * Math.PI * 2) / p.count;
      const support = new THREE.Group();
      support.rotation.z = angle;
      if (!focus) {
        // A broad spider arm joins both pivot cheeks to the fixed shaft boss.
        // Its chamfered outline is packaging only; the pivot remains unchanged.
        const rootR = l.shaftP * 0.88,
          tipR = pivot.x + lugRadius * 1.25,
          rootHalf = width * 0.7,
          tipHalf = lugAcross + lugThickness / 2 + l.wall * 0.45,
          corner = l.wall * 0.55;
        const spoke = new THREE.Mesh(profileSolid(new THREE.Shape([
          new THREE.Vector2(rootR, -rootHalf),
          new THREE.Vector2(tipR - corner, -tipHalf),
          new THREE.Vector2(tipR, -tipHalf + corner),
          new THREE.Vector2(tipR, tipHalf - corner),
          new THREE.Vector2(tipR - corner, tipHalf),
          new THREE.Vector2(rootR, rootHalf),
        ]), l.wall * 1.6), fixed);
        spoke.rotation.x = -Math.PI / 2;
        spoke.position.z = carrierZ;
        support.add(spoke);
        const cheek = new THREE.Shape();
        cheek.moveTo(pivot.x - lugRadius * 1.2, carrierZ);
        cheek.lineTo(pivot.x + lugRadius * 1.2, carrierZ);
        cheek.lineTo(pivot.x + lugRadius, pivot.z);
        cheek.absarc(pivot.x, pivot.z, lugRadius, 0, -Math.PI, true);
        cheek.closePath();
        const cheekGeometry = profileSolid(cheek, lugThickness);
        for (const side of [-1, 1]) {
          const lug = new THREE.Mesh(cheekGeometry, fixed);
          lug.position.y = side * lugAcross;
          support.add(lug);
        }
      }
      const pivotPin = cylinder(radius * 0.32, 2 * (lugAcross + lugThickness / 2) + radius * 0.16, rollerMaterial);
      pivotPin.rotation.x = Math.PI / 2;
      pivotPin.position.copy(pivot);
      support.add(pivotPin);
      carrier.add(support);
      const weight = new THREE.Group();
      weight.rotation.z = angle;
      for (const side of [-1, 1]) {
        const arm = beam(
          pivot,
          pivot.clone().add(v(0, -1)),
          radius * 0.75,
          weightMaterial,
          armThickness,
        );
        arm.name = side < 0 ? 'arm-left' : 'arm-right';
        weight.add(arm);
        // The round pivot bosses are rotationally symmetric about their pins;
        // batch them with the stationary hardware instead of adding draw calls.
        const pivotBoss = cylinder(radius * 0.53, armThickness, fixed);
        pivotBoss.rotation.x = Math.PI / 2;
        pivotBoss.position.copy(pivot).y = side * width * 0.68;
        support.add(pivotBoss);
        const tip = cylinder(tipDimensions.radius, tipDimensions.length, weightMaterial);
        tip.name = side < 0 ? 'weight-left' : 'weight-right';
        tip.rotation.x = Math.PI / 2;
        tip.visible = tipDimensions.length > 0;
        weight.add(tip);
      }
      const roller = cylinder(radius, width, rollerMaterial);
      roller.rotation.x = Math.PI / 2;
      roller.name = 'roller';
      weight.add(roller);
      weights.add(weight);
      const ramp = new THREE.Group();
      ramp.rotation.z = angle;
      ramp.add(new THREE.Mesh(rampGeometry, rampMaterial));
      if (!focus) {
        // Continue the solid heel into a mounting web and broad foot. Both stay
        // behind the complete cam profile, away from the contact/arm sweep.
        const sheaveBack = (r: number) =>
          (r - sheaveHub(g.primaryMinRadius, g)) * Math.tan(g.halfAngle) +
          (g.primaryMaxRadius + g.beltHeight * 0.12) * 0.055;
        const inner = heel - backingSide * rampDepth * 0.65;
        const top = Math.max(...rampPoints.map((point) => point.y));
        const web = new THREE.Shape([
          new THREE.Vector2(inner, sheaveBack(inner)),
          new THREE.Vector2(heel, sheaveBack(heel)),
          new THREE.Vector2(heel, top),
          new THREE.Vector2(inner, top),
        ]);
        ramp.add(new THREE.Mesh(profileSolid(web, width), rampMaterial));
        const footInner = heel - backingSide * rampDepth * 1.15;
        const foot = new THREE.Shape([
          new THREE.Vector2(footInner, sheaveBack(footInner)),
          new THREE.Vector2(heel, sheaveBack(heel)),
          new THREE.Vector2(heel, sheaveBack(heel) + l.wall * 0.7),
          new THREE.Vector2(footInner, sheaveBack(footInner) + l.wall * 0.7),
        ]);
        ramp.add(new THREE.Mesh(profileSolid(foot, width * 1.6), rampMaterial));
      }
      ramps.add(ramp);
    }
    models.push(
      { id: 'primaryCarrier', parentId: 'primaryFixed', object3D: carrier },
      { id: 'flyweights', parentId: 'primaryFixed', object3D: weights },
      { id: 'primaryRamps', parentId: 'primaryMoving', object3D: ramps },
    );
    if (!focus) {
    const hub = new THREE.Group();
    hub.add(
      copies(
        slottedSleeve(
          l.guideR,
          l.wall,
          l.pathP,
          l.guideRoller + g.beltHeight * visual.slotClearance,
          l.wall,
          l.capP - l.p0,
          visual.trackCount,
        ),
        moving,
      ),
    );
    hub.add(
      ring(
        l.guideR - l.wall / 2,
        l.springP + l.wire * 2,
        l.capP - l.p0,
        l.capP - l.p0 + l.wall,
        moving,
      ),
    );
    carrier.add(
      ring(
        l.guideR + l.wall * 0.85,
        l.springP + l.wire * 2,
        l.fixedSeatP - l.wall,
        l.fixedSeatP,
        fixed,
      ),
    );
    models.push(
      { id: 'primaryGuide', parentId: 'primaryMoving', object3D: hub },
      {
        id: 'primaryGuideRollers',
        parentId: 'primaryFixed',
        object3D: radialRollers(
          l.guideR,
          l.pinP,
          l.guideRoller,
          l.wall,
          l.shaftP,
          appearance.fixedSheave,
        ),
      },
    );
    }
    if (!focus && spec.primary_has_spring) {
      const spring = new MechanismSpring(
        l.springP,
        l.wire,
        metal(appearance.spring),
      );
      spring.update(l.fixedSeatP + l.wire, l.capP - l.wire);
      models.push({
        id: 'primarySpring',
        parentId: 'primaryFixed',
        object3D: spring,
      });
    }
  }
  if (focus !== 'primary' && spec.secondary_helix_points_m.length && l.pathS.length > 1) {
    const sleeveBase = focus ? Math.min(...l.pathS.map(p => p.y)) - l.rollerS - l.clearance : l.baseS;
    const sleeve = copies(
      slottedSleeve(
        l.helixR,
        l.wall,
        l.pathS,
        l.rollerS + g.beltHeight * visual.slotClearance,
        sleeveBase,
        l.sleeveTop,
        visual.trackCount,
      ),
      metal(appearance.fixedSheave),
    );
    if (!focus) {
    sleeve.add(
      ring(
        l.helixR - l.wall / 2,
        l.helixR + l.wall / 2,
        l.baseS - l.wall,
        l.baseS,
        fixed,
      ),
    );
    sleeve.add(
      ring(
        l.shaftS * 0.98,
        l.shaftS + l.wall,
        l.baseS - l.wall,
        l.baseS,
        fixed,
      ),
    );
    // Open end support reveals the spring while connecting the cam to the shaft.
    for (let i = 0; i < visual.trackCount; i++) {
      const support = beam(
        v(l.shaftS, l.baseS - l.wall / 2),
        v(l.helixR, l.baseS - l.wall / 2),
        l.wall,
        fixed,
      );
      support.rotateOnWorldAxis(
        new THREE.Vector3(0, 0, 1),
        (i * Math.PI * 2) / visual.trackCount,
      );
      support.position.applyAxisAngle(
        new THREE.Vector3(0, 0, 1),
        (i * Math.PI * 2) / visual.trackCount,
      );
      sleeve.add(support);
    }
    }
    const hubR = l.shaftS + l.wall * 1.25;
    const hub = new THREE.Group();
    if (!focus) {
    hub.add(
      ring(
        l.shaftS + l.clearance * 0.2,
        hubR,
        l.capS - l.s0 - l.wall,
        -l.wall,
        moving,
      ),
    );
    }
    const springRadius = (hubR + l.helixR - l.wall) / 2;
    if (!focus) {
    hub.add(
      ring(
        l.shaftS + l.clearance * 0.2,
        springRadius + l.wire * 2,
        l.capS - l.s0 - l.wall,
        l.capS - l.s0,
        moving,
      ),
    );
    }
    hub.add(
      radialRollers(
        l.helixR,
        l.rollerZ - l.s0,
        l.rollerS,
        l.wall,
        hubR,
        appearance.movingSheave,
      ),
    );
    models.push(
      { id: 'helix', parentId: 'secondaryFixed', object3D: sleeve },
      { id: 'helixFollowers', parentId: 'secondaryMoving', object3D: hub },
    );
    if (!focus && spec.secondary_has_spring) {
      const spring = new MechanismSpring(
        springRadius,
        l.wire,
        metal(appearance.spring),
      );
      spring.update(l.baseS + l.wire, l.capS - l.wall - l.wire);
      models.push({
        id: 'secondarySpring',
        parentId: 'secondaryFixed',
        object3D: spring,
      });
    }
  }
  return models.map((model) =>
    model.object3D instanceof THREE.Group && model.id !== 'flyweights'
      ? { ...model, object3D: batchRigidParts(model.object3D) }
      : model,
  );
}

export function positionMechanisms(
  controller: Scene3DController,
  g: SceneGeometry,
  shift: number,
): void {
  const pose = mechanismPose(g, shift);
  if (!pose) return;
  const l = mechanismLayout(g),
    primary = g.mechanisms?.primary;
  const weights = controller.getModel('flyweights')?.object3D;
  // An invalid contact must not leave a plausible-looking frozen arm on screen.
  if (weights) weights.visible = !!pose.primary_roller_m;
  if (primary && pose.primary_roller_m) {
    const pivot = v(sceneDistance(primary.pivot_m[1]), l.pivotZ);
    const roller = v(
      sceneDistance(pose.primary_roller_m[1]),
      l.back - sceneDistance(pose.primary_roller_m[0]),
    );
    const width = sceneDistance(primary.roller_radius_m) * 1.15;
    const tipDimensions = primaryTipDimensions(
      sceneDistance(primary.roller_radius_m),
      primary.tip_mass_per_flyweight_kg,
    );
    controller.getModel('flyweights')?.object3D.children.forEach((group) => {
      for (const [name, side] of [
        ['arm-left', -1],
        ['arm-right', 1],
      ] as const) {
        const across = side * width * 0.68;
        positionBeam(
          group.getObjectByName(name)!,
          pivot.clone().add(v(0, 0, across)),
          roller.clone().add(v(0, 0, across)),
        );
      }
      group.getObjectByName('roller')!.position.copy(roller);
      for (const [name, side] of [
        ['weight-left', -1],
        ['weight-right', 1],
      ] as const) {
        group.getObjectByName(name)!.position.copy(roller).y =
          side * tipDimensions.centreAcross;
      }
    });
  }
  const primarySpring = controller.getModel('primarySpring')?.object3D;
  if (primarySpring instanceof MechanismSpring)
    primarySpring.update(
      l.fixedSeatP + l.wire,
      l.capP - sceneDistance(pose.primary_ramp_shift_m) - l.wire,
    );
  const secondarySpring = controller.getModel('secondarySpring')?.object3D;
  if (secondarySpring instanceof MechanismSpring)
    secondarySpring.update(
      l.baseS + l.wire,
      l.capS + sceneDistance(pose.secondary_axial_position_m) - l.wall - l.wire,
      pose.secondary_angle_rad,
    );
}
