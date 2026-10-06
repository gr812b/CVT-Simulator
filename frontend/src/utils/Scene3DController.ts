import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type {
  Scene3DConfig,
  Model3DConfig,
  ModelTransform,
} from '@utils/sceneTypes';
import { Model3D } from './Model3D';
import { sceneAppearance } from '../styles/theme';

const SHUTTER_EXPOSURE_SECONDS = 1 / 120; // 180° shutter at a 60 Hz virtual camera.
const BLUR_MIN_TRAVEL_RAD = THREE.MathUtils.degToRad(5);
const BLUR_MAX_SAMPLES = 6;
const BLUR_MIN_ADAPTIVE_CAP = 2;
const BLUR_INITIAL_ADAPTIVE_CAP = 6;
const BLUR_TARGET_STEP_RAD = THREE.MathUtils.degToRad(15);

// Numerical budget only: the virtual camera exposure remains 1/120 s.
// The controller reduces this cap if a device cannot sustain the work and
// slowly restores quality when there is headroom.
const BLUR_SLOW_FRAME_MS = 24;
const BLUR_VERY_SLOW_FRAME_MS = 40;
const BLUR_FAST_FRAME_MS = 13;
const BLUR_FAST_FRAMES_TO_RAISE_QUALITY = 30;

export interface TemporalRotationTarget {
  object: THREE.Object3D;
  axisLocal: THREE.Vector3;
  angularSpeedRadPerSecond: number;
  angleOffsetAt: (wallOffsetSeconds: number) => number;
}

type FrameUpdate = (now: number) => void;
type TemporalRotationProvider = () => readonly TemporalRotationTarget[];

/**
 * Manages a Three.js scene with hierarchical models.
 *
 * The generic render loop supports two optional presentation hooks:
 * - a per-RAF frame update for smooth animation;
 * - finite-shutter temporal supersampling for true rotational motion blur.
 */
export class Scene3DController {
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera | THREE.OrthographicCamera;
  private renderer: THREE.WebGLRenderer;
  private controls: OrbitControls | null = null;
  private models: Map<string, Model3D> = new Map();
  private sceneObjects: THREE.Object3D[] = [];
  private container: HTMLElement;
  private animationFrameId: number | null = null;

  private frameUpdate: FrameUpdate | null = null;
  private frameObservers = new Set<FrameUpdate>();
  private temporalRotationProvider: TemporalRotationProvider | null = null;

  private blurSampleTarget: THREE.WebGLRenderTarget | null = null;
  private blurAccumulationTarget: THREE.WebGLRenderTarget | null = null;
  private blurAccumulateScene: THREE.Scene | null = null;
  private blurCopyScene: THREE.Scene | null = null;
  private blurQuadCamera: THREE.OrthographicCamera | null = null;
  private blurQuadGeometry: THREE.PlaneGeometry | null = null;
  private blurAccumulateMaterial: THREE.ShaderMaterial | null = null;
  private blurCopyMaterial: THREE.MeshBasicMaterial | null = null;
  private blurSupported: boolean | null = null;
  private adaptiveBlurSampleCap = BLUR_INITIAL_ADAPTIVE_CAP;
  private fastBlurFrameCount = 0;
  private perspectiveFov = 75;
  private resizeObserver: ResizeObserver;
  private visibilityObserver: IntersectionObserver;
  private visible = true;
  private dirty = true;
  private orbitOnly: boolean;
  private renderOnDemand: boolean;
  private fittedBounds: THREE.Box3 | null = null;
  private initialCamera: Scene3DConfig['camera'];
  private invalidate = () => {
    this.dirty = true;
  };
  private keyboardOrbit = (event: KeyboardEvent) => {
    if (
      !this.controls ||
      !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)
    )
      return;
    event.preventDefault();
    const offset = this.camera.position.clone().sub(this.controls.target);
    const spherical = new THREE.Spherical().setFromVector3(offset);
    if (event.key === 'ArrowLeft') spherical.theta -= 0.1;
    if (event.key === 'ArrowRight') spherical.theta += 0.1;
    if (event.key === 'ArrowUp') spherical.phi -= 0.1;
    if (event.key === 'ArrowDown') spherical.phi += 0.1;
    spherical.makeSafe();
    this.camera.position
      .copy(this.controls.target)
      .add(offset.setFromSpherical(spherical));
    this.controls.update();
    this.invalidate();
  };

  constructor(config: Scene3DConfig) {
    this.container = config.container;
    this.initialCamera = config.camera;
    this.orbitOnly = config.orbitOnly ?? false;
    this.renderOnDemand = config.renderOnDemand ?? false;
    this.scene = new THREE.Scene();

    if (config.backgroundColor !== undefined) {
      this.scene.background = new THREE.Color(config.backgroundColor);
    }

    const aspect =
      Math.max(1, this.container.clientWidth) /
      Math.max(1, this.container.clientHeight);
    if (config.camera.type === 'perspective') {
      this.camera = new THREE.PerspectiveCamera(
        config.camera.fov ?? 75,
        aspect,
        config.camera.near ?? 0.1,
        config.camera.far ?? 1000,
      );
    } else {
      const frustumSize = 10;
      this.camera = new THREE.OrthographicCamera(
        (frustumSize * aspect) / -2,
        (frustumSize * aspect) / 2,
        frustumSize / 2,
        frustumSize / -2,
        config.camera.near ?? 0.1,
        config.camera.far ?? 1000,
      );
    }

    this.perspectiveFov = config.camera.fov ?? 75;
    this.camera.position.set(...config.camera.position);
    this.camera.lookAt(...config.camera.lookAt);

    this.renderer = new THREE.WebGLRenderer({
      antialias: config.antialias ?? true,
      alpha: config.transparentBackground ?? true,
    });
    this.renderer.setPixelRatio(
      config.pixelRatio ??
        Math.min(window.devicePixelRatio, sceneAppearance.maxPixelRatio),
    );
    this.renderer.setSize(
      this.container.clientWidth,
      this.container.clientHeight,
    );
    this.renderer.domElement.tabIndex = 0;
    this.renderer.domElement.setAttribute('role', 'img');
    this.renderer.domElement.setAttribute(
      'aria-label',
      'Interactive CVT model. Drag or use arrow keys to rotate.',
    );
    this.renderer.domElement.addEventListener('keydown', this.keyboardOrbit);
    this.container.appendChild(this.renderer.domElement);

    if (config.enableControls) {
      this.controls = new OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;
      this.controls.target.set(...config.camera.lookAt);
      this.configureControls();
    }

    const lighting = sceneAppearance.light;
    this.scene.add(
      new THREE.HemisphereLight(
        lighting.sky,
        lighting.ground,
        lighting.intensity,
      ),
    );
    const key = new THREE.DirectionalLight(lighting.sky, 3);
    key.position.set(5, 9, 12);
    this.scene.add(key);
    const rim = new THREE.DirectionalLight(lighting.sky, 2);
    rim.position.set(-8, 3, -6);
    this.scene.add(rim);

    this.handleResize = this.handleResize.bind(this);
    this.resizeObserver = new ResizeObserver(this.handleResize);
    this.resizeObserver.observe(this.container);
    this.visibilityObserver = new IntersectionObserver(([entry]) => {
      this.visible = entry.isIntersecting;
      this.invalidate();
    });
    this.visibilityObserver.observe(this.container);

    this.startRenderLoop();
  }

  private configureControls(): void {
    if (!this.controls) return;
    this.controls.enablePan = !this.orbitOnly;
    this.controls.enableZoom = !this.orbitOnly;
    this.controls.addEventListener('change', this.invalidate);
  }

  /** Restore the configured view without rebuilding the scene or replay. */
  public resetView(): void {
    this.setCameraProjection(this.initialCamera.type);
    this.camera.position.set(...this.initialCamera.position);
    this.controls?.target.set(...this.initialCamera.lookAt);
    this.camera.lookAt(...this.initialCamera.lookAt);
    if (this.fittedBounds) this.fitBounds(this.fittedBounds);
    this.controls?.update();
    this.invalidate();
  }

  /** Fit the actual resolved envelope, preserving the chosen view direction. */
  public fitBounds(bounds: THREE.Box3): void {
    this.fittedBounds = bounds.clone();
    const target = bounds.getCenter(new THREE.Vector3());
    const direction = this.camera.position
      .clone()
      .sub(this.controls?.target ?? new THREE.Vector3())
      .normalize();
    this.camera.position.copy(target).add(direction);
    this.camera.lookAt(target);
    const inverseRotation = this.camera.quaternion.clone().invert();
    const aspect =
      Math.max(1, this.container.clientWidth) /
      Math.max(1, this.container.clientHeight);
    const tanV = Math.tan(THREE.MathUtils.degToRad(this.perspectiveFov) / 2);
    let distance = 0;
    for (const x of [bounds.min.x, bounds.max.x])
      for (const y of [bounds.min.y, bounds.max.y])
        for (const z of [bounds.min.z, bounds.max.z]) {
          const p = new THREE.Vector3(x, y, z)
            .sub(target)
            .applyQuaternion(inverseRotation);
          distance = Math.max(
            distance,
            Math.abs(p.x) / (tanV * aspect) + p.z,
            Math.abs(p.y) / tanV + p.z,
          );
        }
    distance *= 1.12;
    this.camera.position.copy(target).addScaledVector(direction, distance);
    if (this.camera instanceof THREE.OrthographicCamera) {
      this.camera.top = distance * tanV;
      this.camera.bottom = -this.camera.top;
      this.camera.right = this.camera.top * aspect;
      this.camera.left = -this.camera.right;
      this.camera.zoom = 1;
    }
    this.camera.updateProjectionMatrix();
    this.controls?.target.copy(target);
    if (this.controls) {
      this.controls.minDistance = distance * 0.25;
      this.controls.maxDistance = distance * 5;
      this.controls.update();
    }
    this.invalidate();
  }

  public addModel(config: Model3DConfig): Model3D {
    const model = new Model3D(config);
    this.models.set(config.id, model);

    if (config.parentId) {
      const parent = this.models.get(config.parentId);
      if (parent) {
        model.setParent(parent);
      } else {
        alert(
          `Parent model "${config.parentId}" not found for model "${config.id}"`,
        );
        this.scene.add(model.object3D);
      }
    } else {
      this.scene.add(model.object3D);
    }

    this.invalidate();
    return model;
  }

  public getModel(id: string): Model3D | undefined {
    return this.models.get(id);
  }

  public removeModel(id: string): void {
    const model = this.models.get(id);
    if (model) {
      model.object3D.removeFromParent();
      model.dispose();
      this.models.delete(id);
    }
  }

  public updateModels(transforms: Record<string, ModelTransform>): void {
    this.invalidate();
    for (const [modelId, transform] of Object.entries(transforms)) {
      const model = this.models.get(modelId);
      if (model) model.updateTransform(transform);
    }
  }

  public getScene(): THREE.Scene {
    return this.scene;
  }

  public getCamera(): THREE.Camera {
    return this.camera;
  }

  public getRenderer(): THREE.WebGLRenderer {
    return this.renderer;
  }

  public getControls(): OrbitControls | null {
    return this.controls;
  }

  public getCameraProjection(): 'perspective' | 'orthographic' {
    return this.camera instanceof THREE.OrthographicCamera
      ? 'orthographic'
      : 'perspective';
  }

  /**
   * Switch projection without changing the apparent framing.
   *
   * Perspective -> orthographic uses the current target distance and effective
   * field of view to construct the equivalent orthographic frustum.
   * Orthographic -> perspective moves the camera along the same view ray so the
   * current orthographic scale maps back to the saved perspective field of view.
   */
  public setCameraProjection(type: 'perspective' | 'orthographic'): void {
    if (this.getCameraProjection() === type) return;

    const width = Math.max(1, this.container.clientWidth);
    const height = Math.max(1, this.container.clientHeight);
    const aspect = width / height;
    const oldCamera = this.camera;

    const target =
      this.controls?.target.clone() ??
      oldCamera.position
        .clone()
        .add(oldCamera.getWorldDirection(new THREE.Vector3()));

    const viewDirection = oldCamera.position.clone().sub(target);
    const targetDistance = Math.max(viewDirection.length(), 1e-6);
    viewDirection.normalize();

    let nextCamera: THREE.PerspectiveCamera | THREE.OrthographicCamera;

    if (type === 'orthographic') {
      const perspective = oldCamera as THREE.PerspectiveCamera;
      this.perspectiveFov = perspective.fov;

      const effectiveFov = THREE.MathUtils.degToRad(
        perspective.getEffectiveFOV(),
      );
      const visibleHeight = Math.max(
        1e-6,
        2 * targetDistance * Math.tan(effectiveFov / 2),
      );

      nextCamera = new THREE.OrthographicCamera(
        (-visibleHeight * aspect) / 2,
        (visibleHeight * aspect) / 2,
        visibleHeight / 2,
        -visibleHeight / 2,
        perspective.near,
        perspective.far,
      );
      nextCamera.position.copy(perspective.position);
      nextCamera.quaternion.copy(perspective.quaternion);
      nextCamera.up.copy(perspective.up);
    } else {
      const orthographic = oldCamera as THREE.OrthographicCamera;
      const visibleHeight = Math.max(
        1e-6,
        (orthographic.top - orthographic.bottom) / orthographic.zoom,
      );
      const fovRadians = THREE.MathUtils.degToRad(this.perspectiveFov);
      const matchedDistance = visibleHeight / (2 * Math.tan(fovRadians / 2));

      nextCamera = new THREE.PerspectiveCamera(
        this.perspectiveFov,
        aspect,
        orthographic.near,
        orthographic.far,
      );
      nextCamera.position
        .copy(target)
        .addScaledVector(viewDirection, matchedDistance);
      nextCamera.quaternion.copy(orthographic.quaternion);
      nextCamera.up.copy(orthographic.up);
    }

    this.camera = nextCamera;
    this.camera.updateProjectionMatrix();

    if (this.controls) {
      const previousControls = this.controls;
      const enableDamping = previousControls.enableDamping;
      const dampingFactor = previousControls.dampingFactor;

      previousControls.dispose();

      this.controls = new OrbitControls(this.camera, this.renderer.domElement);
      this.controls.target.copy(target);
      this.controls.enableDamping = enableDamping;
      this.controls.dampingFactor = dampingFactor;
      this.configureControls();
      this.controls.update();
    }
  }
  /** Register an animation-only update that runs once per browser frame. */
  public setFrameUpdate(update: FrameUpdate | null): void {
    this.frameUpdate = update;
  }

  /** Update overlays after the mechanism pose and before the same frame renders. */
  public onFrame(update: FrameUpdate): () => void {
    this.frameObservers.add(update);
    return () => {
      this.frameObservers.delete(update);
    };
  }

  /**
   * Register local rigid-body rotational trajectories for finite-shutter blur.
   *
   * `angleOffsetAt(dt)` returns the true local angular displacement from the
   * center pose at a wall-clock offset within the exposure. Full revolutions
   * therefore remain visible to the shutter integrator.
   */
  public setTemporalRotationProvider(
    provider: TemporalRotationProvider | null,
  ): void {
    this.temporalRotationProvider = provider;
  }

  private startRenderLoop(): void {
    const animate = (now: number) => {
      this.animationFrameId = requestAnimationFrame(animate);

      if (
        !this.visible ||
        document.hidden ||
        this.container.clientWidth === 0 ||
        this.container.clientHeight === 0
      )
        return;
      if (this.controls) this.controls.update();
      if (this.renderOnDemand && !this.dirty && !this.frameUpdate) return;
      this.dirty = false;
      if (this.frameUpdate) this.frameUpdate(now);
      for (const update of this.frameObservers) update(now);

      const targets = this.temporalRotationProvider?.() ?? [];
      if (this.shouldUseShutterBlur(targets)) {
        this.renderFiniteShutter(targets);
      } else {
        this.renderer.render(this.scene, this.camera);
      }
    };

    this.animationFrameId = requestAnimationFrame(animate);
  }

  private shouldUseShutterBlur(
    targets: readonly TemporalRotationTarget[],
  ): boolean {
    if (!this.supportsLinearHdrBlur() || targets.length === 0) return false;

    return targets.some(
      (target) =>
        Number.isFinite(target.angularSpeedRadPerSecond) &&
        Math.abs(target.angularSpeedRadPerSecond) * SHUTTER_EXPOSURE_SECONDS >=
          BLUR_MIN_TRAVEL_RAD,
    );
  }

  private supportsLinearHdrBlur(): boolean {
    if (this.blurSupported === null) {
      // Linear HDR accumulation needs a floating-point color attachment.
      // WebGLRenderer is WebGL2-only in the Three.js version used by this app.
      this.blurSupported = this.renderer.extensions.has(
        'EXT_color_buffer_float',
      );
      if (!this.blurSupported) {
        console.warn(
          'Finite-shutter motion blur disabled: EXT_color_buffer_float is unavailable.',
        );
      }
    }
    return this.blurSupported;
  }

  private blurSampleCount(targets: readonly TemporalRotationTarget[]): number {
    const maximumTravel = targets.reduce(
      (maximum, target) =>
        Math.max(
          maximum,
          Math.abs(target.angularSpeedRadPerSecond) * SHUTTER_EXPOSURE_SECONDS,
        ),
      0,
    );

    if (maximumTravel < BLUR_MIN_TRAVEL_RAD) return 1;

    // Temporal supersampling is the actual camera-exposure integrator. Aim for
    // about 15 degrees of shaft travel between samples so sharp radial CAD
    // features do not resolve into visible copies. The adaptive cap is purely a
    // performance ceiling and never changes the physical shutter duration.
    const desired = Math.max(
      4,
      Math.ceil(maximumTravel / BLUR_TARGET_STEP_RAD) + 1,
    );

    return Math.min(BLUR_MAX_SAMPLES, this.adaptiveBlurSampleCap, desired);
  }

  private updateAdaptiveBlurBudget(renderMilliseconds: number): void {
    if (!Number.isFinite(renderMilliseconds)) return;

    // A severe miss should recover in one or two frames rather than stepping
    // slowly through an unusable quality level.
    if (renderMilliseconds > BLUR_VERY_SLOW_FRAME_MS) {
      this.adaptiveBlurSampleCap = Math.max(
        BLUR_MIN_ADAPTIVE_CAP,
        Math.floor(this.adaptiveBlurSampleCap * 0.65),
      );
      this.fastBlurFrameCount = 0;
      return;
    }

    if (renderMilliseconds > BLUR_SLOW_FRAME_MS) {
      this.adaptiveBlurSampleCap = Math.max(
        BLUR_MIN_ADAPTIVE_CAP,
        this.adaptiveBlurSampleCap - 4,
      );
      this.fastBlurFrameCount = 0;
      return;
    }

    // Restore quality slowly so the controller does not oscillate around the
    // machine's limit. Two samples every sustained fast window is intentionally
    // conservative compared with the fast down-ramp above.
    if (renderMilliseconds < BLUR_FAST_FRAME_MS) {
      this.fastBlurFrameCount += 1;
      if (
        this.fastBlurFrameCount >= BLUR_FAST_FRAMES_TO_RAISE_QUALITY &&
        this.adaptiveBlurSampleCap < BLUR_MAX_SAMPLES
      ) {
        this.adaptiveBlurSampleCap = Math.min(
          BLUR_MAX_SAMPLES,
          this.adaptiveBlurSampleCap + 2,
        );
        this.fastBlurFrameCount = 0;
      }
      return;
    }

    this.fastBlurFrameCount = 0;
  }

  /**
   * Render a finite box-shutter exposure.
   *
   * Each shutter sample is a genuine Three.js scene render. Samples are stored
   * and averaged in half-float Linear-sRGB, then converted to the renderer's
   * normal output color space exactly once when copied to the display.
   *
   * A stationary pixel C therefore satisfies:
   *
   *     (1/N) Σ C = C
   *
   * independently of RPM/sample count.
   */
  private renderFiniteShutter(
    targets: readonly TemporalRotationTarget[],
  ): void {
    this.ensureBlurResources();

    if (
      this.blurSampleTarget === null ||
      this.blurAccumulationTarget === null ||
      this.blurAccumulateScene === null ||
      this.blurCopyScene === null ||
      this.blurQuadCamera === null ||
      this.blurAccumulateMaterial === null ||
      this.blurCopyMaterial === null
    ) {
      this.renderer.render(this.scene, this.camera);
      return;
    }

    const sampleCount = this.blurSampleCount(targets);
    const renderStartedAt = performance.now();
    const bases = targets.map((target) => target.object.quaternion.clone());
    const delta = new THREE.Quaternion();

    const previousAutoClear = this.renderer.autoClear;
    const previousTarget = this.renderer.getRenderTarget();
    const previousClearColor = this.renderer.getClearColor(new THREE.Color());
    const previousClearAlpha = this.renderer.getClearAlpha();

    this.renderer.autoClear = false;

    // Clear the linear HDR accumulator exactly once.
    this.renderer.setRenderTarget(this.blurAccumulationTarget);
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.clear(true, false, false);
    this.renderer.setClearColor(previousClearColor, previousClearAlpha);

    this.blurAccumulateMaterial.uniforms.weight.value = 1 / sampleCount;

    for (let sampleIndex = 0; sampleIndex < sampleCount; sampleIndex += 1) {
      // Midpoint stratification keeps the finite-shutter estimate clean and
      // low-noise at ordinary 1x playback, while the sample-count schedule and
      // physical shutter duration control the remaining approximation quality.
      const wallOffset =
        ((sampleIndex + 0.5) / sampleCount - 0.5) * SHUTTER_EXPOSURE_SECONDS;

      targets.forEach((target, targetIndex) => {
        const axis = target.axisLocal;
        const angle = target.angleOffsetAt(wallOffset);

        if (!Number.isFinite(angle) || axis.lengthSq() <= 0) {
          target.object.quaternion.copy(bases[targetIndex]);
          return;
        }

        delta.setFromAxisAngle(axis, angle);
        target.object.quaternion.copy(bases[targetIndex]).multiply(delta);
      });

      // Normal scene render into a Linear-sRGB half-float sample buffer.
      this.renderer.setRenderTarget(this.blurSampleTarget);
      this.renderer.clear(true, true, true);
      this.renderer.render(this.scene, this.camera);

      // Add exactly (1/N) of that linear sample into the HDR accumulator.
      this.blurAccumulateMaterial.uniforms.sampleTexture.value =
        this.blurSampleTarget.texture;
      this.renderer.setRenderTarget(this.blurAccumulationTarget);
      this.renderer.render(this.blurAccumulateScene, this.blurQuadCamera);
    }

    // Always leave actual scene objects at their center-of-shutter pose.
    targets.forEach((target, index) => {
      target.object.quaternion.copy(bases[index]);
    });

    // Preserve the averaged alpha for theme/transparent backgrounds.
    // MeshBasicMaterial handles the single
    // Linear-sRGB -> renderer.outputColorSpace conversion for display.
    this.blurCopyMaterial.map = this.blurAccumulationTarget.texture;
    this.blurCopyMaterial.needsUpdate = true;

    this.renderer.setRenderTarget(previousTarget);
    this.renderer.clear(true, true, true);
    this.renderer.render(this.blurCopyScene, this.blurQuadCamera);

    this.renderer.autoClear = previousAutoClear;
    this.renderer.setClearColor(previousClearColor, previousClearAlpha);

    this.updateAdaptiveBlurBudget(performance.now() - renderStartedAt);
  }

  private ensureBlurResources(): void {
    const size = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    const width = Math.max(1, Math.floor(size.x * 0.65));
    const height = Math.max(1, Math.floor(size.y * 0.65));

    if (
      this.blurSampleTarget !== null &&
      this.blurSampleTarget.width === width &&
      this.blurSampleTarget.height === height
    ) {
      return;
    }

    this.disposeBlurResources();

    const makeLinearHdrTarget = (depthBuffer: boolean) => {
      const target = new THREE.WebGLRenderTarget(width, height, {
        minFilter: THREE.LinearFilter,
        magFilter: THREE.LinearFilter,
        format: THREE.RGBAFormat,
        type: THREE.HalfFloatType,
        depthBuffer,
        stencilBuffer: false,
      });
      target.texture.colorSpace = THREE.LinearSRGBColorSpace;
      target.texture.generateMipmaps = false;
      return target;
    };

    this.blurSampleTarget = makeLinearHdrTarget(true);
    this.blurAccumulationTarget = makeLinearHdrTarget(false);

    // This shader does one thing only: write weight * linear sample.
    // No color-space conversion belongs here because both source and
    // destination are Linear-sRGB render targets.
    this.blurAccumulateMaterial = new THREE.ShaderMaterial({
      uniforms: {
        sampleTexture: { value: this.blurSampleTarget.texture },
        weight: { value: 1 },
      },
      vertexShader: `
        varying vec2 vUv;

        void main() {
          vUv = uv;
          gl_Position = vec4(position.xy, 0.0, 1.0);
        }
      `,
      fragmentShader: `
        uniform sampler2D sampleTexture;
        uniform float weight;
        varying vec2 vUv;

        void main() {
          gl_FragColor = texture2D(sampleTexture, vUv) * weight;
        }
      `,
      transparent: true,
      blending: THREE.CustomBlending,
      blendEquation: THREE.AddEquation,
      blendSrc: THREE.OneFactor,
      blendDst: THREE.OneFactor,
      blendEquationAlpha: THREE.AddEquation,
      blendSrcAlpha: THREE.OneFactor,
      blendDstAlpha: THREE.OneFactor,
      depthTest: false,
      depthWrite: false,
      toneMapped: false,
    });

    this.blurCopyMaterial = new THREE.MeshBasicMaterial({
      map: this.blurAccumulationTarget.texture,
      transparent: true,
      blending: THREE.NoBlending,
      opacity: 1,
      depthTest: false,
      depthWrite: false,
      toneMapped: false,
    });

    this.blurQuadGeometry = new THREE.PlaneGeometry(2, 2);

    const accumulateQuad = new THREE.Mesh(
      this.blurQuadGeometry,
      this.blurAccumulateMaterial,
    );
    accumulateQuad.frustumCulled = false;
    this.blurAccumulateScene = new THREE.Scene();
    this.blurAccumulateScene.add(accumulateQuad);

    const copyQuad = new THREE.Mesh(
      this.blurQuadGeometry,
      this.blurCopyMaterial,
    );
    copyQuad.frustumCulled = false;
    this.blurCopyScene = new THREE.Scene();
    this.blurCopyScene.add(copyQuad);

    this.blurQuadCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  }

  private disposeBlurResources(): void {
    this.blurSampleTarget?.dispose();
    this.blurAccumulationTarget?.dispose();
    this.blurSampleTarget = null;
    this.blurAccumulationTarget = null;

    this.blurAccumulateMaterial?.dispose();
    this.blurCopyMaterial?.dispose();
    this.blurQuadGeometry?.dispose();

    this.blurAccumulateMaterial = null;
    this.blurCopyMaterial = null;
    this.blurQuadGeometry = null;
    this.blurAccumulateScene = null;
    this.blurCopyScene = null;
    this.blurQuadCamera = null;
  }

  private handleResize(): void {
    const width = Math.max(1, this.container.clientWidth);
    const height = Math.max(1, this.container.clientHeight);

    if (this.camera instanceof THREE.PerspectiveCamera) {
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
    } else if (this.camera instanceof THREE.OrthographicCamera) {
      const aspect = width / height;
      const frustumHeight = this.camera.top - this.camera.bottom;
      const halfHeight = frustumHeight / 2;
      const halfWidth = halfHeight * aspect;
      this.camera.left = -halfWidth;
      this.camera.right = halfWidth;
      this.camera.top = halfHeight;
      this.camera.bottom = -halfHeight;
      this.camera.updateProjectionMatrix();
    }

    if (this.fittedBounds) this.fitBounds(this.fittedBounds);
    this.invalidate();
    this.renderer.setSize(width, height);
    this.disposeBlurResources();
  }

  public addObject(object: THREE.Object3D): void {
    this.invalidate();
    this.scene.add(object);
    this.sceneObjects.push(object);
  }

  public removeObject(object: THREE.Object3D): void {
    this.invalidate();
    this.scene.remove(object);
    const index = this.sceneObjects.indexOf(object);
    if (index > -1) this.sceneObjects.splice(index, 1);
  }

  public dispose(): void {
    if (this.animationFrameId !== null) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }

    this.resizeObserver.disconnect();
    this.visibilityObserver.disconnect();
    this.renderer.domElement.removeEventListener('keydown', this.keyboardOrbit);

    if (this.controls) {
      this.controls.dispose();
      this.controls = null;
    }

    this.frameUpdate = null;
    this.frameObservers.clear();
    this.temporalRotationProvider = null;
    this.disposeBlurResources();

    this.models.forEach((model) => model.dispose());
    this.models.clear();

    this.sceneObjects.forEach((object) => this.scene.remove(object));
    this.sceneObjects = [];

    this.renderer.forceContextLoss();
    this.renderer.dispose();

    if (this.renderer.domElement.parentElement) {
      this.renderer.domElement.parentElement.removeChild(
        this.renderer.domElement,
      );
    }

    this.scene.clear();
  }
}
