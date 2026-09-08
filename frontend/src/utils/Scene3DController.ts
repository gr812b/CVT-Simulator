import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { Scene3DConfig, Model3DConfig, ModelTransform } from '@utils/sceneTypes';
import { Model3D } from './Model3D';

const SHUTTER_EXPOSURE_SECONDS = 1 / 120; // 180° shutter at a 60 Hz virtual camera.
const BLUR_MIN_TRAVEL_RAD = THREE.MathUtils.degToRad(5);
const BLUR_TARGET_STEP_RAD = THREE.MathUtils.degToRad(15);
const BLUR_MAX_SAMPLES = 24;

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

  constructor(config: Scene3DConfig) {
    this.container = config.container;
    this.scene = new THREE.Scene();

    if (config.backgroundColor !== undefined) {
      this.scene.background = new THREE.Color(config.backgroundColor);
    }

    const aspect = this.container.clientWidth / this.container.clientHeight;
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

    this.camera.position.set(...config.camera.position);
    this.camera.lookAt(...config.camera.lookAt);

    this.renderer = new THREE.WebGLRenderer({
      antialias: config.antialias ?? true,
    });
    this.renderer.setPixelRatio(config.pixelRatio ?? window.devicePixelRatio);
    this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
    this.container.appendChild(this.renderer.domElement);

    if (config.enableControls) {
      this.controls = new OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;
    }

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    this.scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(10, 10, 10);
    this.scene.add(directionalLight);

    this.handleResize = this.handleResize.bind(this);
    window.addEventListener('resize', this.handleResize);

    this.startRenderLoop();
  }

  public addModel(config: Model3DConfig): Model3D {
    const model = new Model3D(config);
    this.models.set(config.id, model);

    if (config.parentId) {
      const parent = this.models.get(config.parentId);
      if (parent) {
        model.setParent(parent);
      } else {
        alert(`Parent model "${config.parentId}" not found for model "${config.id}"`);
        this.scene.add(model.object3D);
      }
    } else {
      this.scene.add(model.object3D);
    }

    return model;
  }

  public getModel(id: string): Model3D | undefined {
    return this.models.get(id);
  }

  public removeModel(id: string): void {
    const model = this.models.get(id);
    if (model) {
      this.scene.remove(model.object3D);
      model.dispose();
      this.models.delete(id);
    }
  }

  public updateModels(transforms: Record<string, ModelTransform>): void {
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

  /** Register an animation-only update that runs once per browser frame. */
  public setFrameUpdate(update: FrameUpdate | null): void {
    this.frameUpdate = update;
  }

  /**
   * Register local rigid-body rotational trajectories for finite-shutter blur.
   *
   * `angleOffsetAt(dt)` returns the true local angular displacement from the
   * center pose at a wall-clock offset within the exposure. Full revolutions
   * therefore remain visible to the shutter integrator.
   */
  public setTemporalRotationProvider(provider: TemporalRotationProvider | null): void {
    this.temporalRotationProvider = provider;
  }

  private startRenderLoop(): void {
    const animate = (now: number) => {
      this.animationFrameId = requestAnimationFrame(animate);

      if (this.controls) this.controls.update();
      if (this.frameUpdate) this.frameUpdate(now);

      const targets = this.temporalRotationProvider?.() ?? [];
      if (this.shouldUseShutterBlur(targets)) {
        this.renderFiniteShutter(targets);
      } else {
        this.renderer.render(this.scene, this.camera);
      }
    };

    this.animationFrameId = requestAnimationFrame(animate);
  }

  private shouldUseShutterBlur(targets: readonly TemporalRotationTarget[]): boolean {
    if (!this.supportsLinearHdrBlur() || targets.length === 0) return false;

    return targets.some((target) => (
      Number.isFinite(target.angularSpeedRadPerSecond)
      && Math.abs(target.angularSpeedRadPerSecond) * SHUTTER_EXPOSURE_SECONDS
        >= BLUR_MIN_TRAVEL_RAD
    ));
  }

  private supportsLinearHdrBlur(): boolean {
    if (this.blurSupported === null) {
      // Linear HDR accumulation needs a floating-point color attachment.
      // WebGLRenderer is WebGL2-only in the Three.js version used by this app.
      this.blurSupported = this.renderer.extensions.has('EXT_color_buffer_float');
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
      (maximum, target) => Math.max(
        maximum,
        Math.abs(target.angularSpeedRadPerSecond) * SHUTTER_EXPOSURE_SECONDS,
      ),
      0,
    );

    return Math.min(
      BLUR_MAX_SAMPLES,
      Math.max(2, Math.ceil(maximumTravel / BLUR_TARGET_STEP_RAD) + 1),
    );
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
  private renderFiniteShutter(targets: readonly TemporalRotationTarget[]): void {
    this.ensureBlurResources();

    if (
      this.blurSampleTarget === null
      || this.blurAccumulationTarget === null
      || this.blurAccumulateScene === null
      || this.blurCopyScene === null
      || this.blurQuadCamera === null
      || this.blurAccumulateMaterial === null
      || this.blurCopyMaterial === null
    ) {
      this.renderer.render(this.scene, this.camera);
      return;
    }

    const sampleCount = this.blurSampleCount(targets);
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
      // Stratified midpoint samples across a centered box shutter.
      const wallOffset = (
        (sampleIndex + 0.5) / sampleCount - 0.5
      ) * SHUTTER_EXPOSURE_SECONDS;

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
      this.blurAccumulateMaterial.uniforms.sampleTexture.value = this.blurSampleTarget.texture;
      this.renderer.setRenderTarget(this.blurAccumulationTarget);
      this.renderer.render(this.blurAccumulateScene, this.blurQuadCamera);
    }

    // Always leave actual scene objects at their center-of-shutter pose.
    targets.forEach((target, index) => {
      target.object.quaternion.copy(bases[index]);
    });

    // Full-opacity final copy. MeshBasicMaterial handles the single
    // Linear-sRGB -> renderer.outputColorSpace conversion for display.
    this.blurCopyMaterial.map = this.blurAccumulationTarget.texture;
    this.blurCopyMaterial.needsUpdate = true;

    this.renderer.setRenderTarget(previousTarget);
    this.renderer.clear(true, true, true);
    this.renderer.render(this.blurCopyScene, this.blurQuadCamera);

    this.renderer.autoClear = previousAutoClear;
    this.renderer.setClearColor(previousClearColor, previousClearAlpha);
  }

  private ensureBlurResources(): void {
    const size = this.renderer.getDrawingBufferSize(new THREE.Vector2());
    const width = Math.max(1, Math.floor(size.x));
    const height = Math.max(1, Math.floor(size.y));

    if (
      this.blurSampleTarget !== null
      && this.blurSampleTarget.width === width
      && this.blurSampleTarget.height === height
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
      transparent: false,
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
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;

    if (this.camera instanceof THREE.PerspectiveCamera) {
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
    } else if (this.camera instanceof THREE.OrthographicCamera) {
      const aspect = width / height;
      const frustumSize = 10;
      this.camera.left = (frustumSize * aspect) / -2;
      this.camera.right = (frustumSize * aspect) / 2;
      this.camera.top = frustumSize / 2;
      this.camera.bottom = frustumSize / -2;
      this.camera.updateProjectionMatrix();
    }

    this.renderer.setSize(width, height);
    this.disposeBlurResources();
  }

  public addObject(object: THREE.Object3D): void {
    this.scene.add(object);
    this.sceneObjects.push(object);
  }

  public removeObject(object: THREE.Object3D): void {
    this.scene.remove(object);
    const index = this.sceneObjects.indexOf(object);
    if (index > -1) this.sceneObjects.splice(index, 1);
  }

  public dispose(): void {
    if (this.animationFrameId !== null) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }

    window.removeEventListener('resize', this.handleResize);

    if (this.controls) {
      this.controls.dispose();
      this.controls = null;
    }

    this.frameUpdate = null;
    this.temporalRotationProvider = null;
    this.disposeBlurResources();

    this.models.forEach((model) => model.dispose());
    this.models.clear();

    this.sceneObjects.forEach((object) => this.scene.remove(object));
    this.sceneObjects = [];

    this.renderer.dispose();

    if (this.renderer.domElement.parentElement) {
      this.renderer.domElement.parentElement.removeChild(this.renderer.domElement);
    }

    this.scene.clear();
  }
}
