import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { Scene3DConfig, Model3DConfig, ModelTransform } from '@utils/sceneTypes';
import { Model3D } from './Model3D';

/**
 * Manages a Three.js 3D scene with hierarchical models.
 * Provides a clean API for updating model transforms without coupling to any specific data source.
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

  constructor(config: Scene3DConfig) {
    this.container = config.container;
    this.scene = new THREE.Scene();

    // Set background color
    if (config.backgroundColor !== undefined) {
      this.scene.background = new THREE.Color(config.backgroundColor);
    }

    // Create camera
    const aspect = this.container.clientWidth / this.container.clientHeight;
    if (config.camera.type === 'perspective') {
      this.camera = new THREE.PerspectiveCamera(
        config.camera.fov ?? 75,
        aspect,
        config.camera.near ?? 0.1,
        config.camera.far ?? 1000
      );
    } else {
      const frustumSize = 10;
      this.camera = new THREE.OrthographicCamera(
        (frustumSize * aspect) / -2,
        (frustumSize * aspect) / 2,
        frustumSize / 2,
        frustumSize / -2,
        config.camera.near ?? 0.1,
        config.camera.far ?? 1000
      );
    }

    this.camera.position.set(...config.camera.position);
    this.camera.lookAt(...config.camera.lookAt);

    // Create renderer
    this.renderer = new THREE.WebGLRenderer({
      antialias: config.antialias ?? true,
    });
    this.renderer.setPixelRatio(config.pixelRatio ?? window.devicePixelRatio);
    this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
    this.container.appendChild(this.renderer.domElement);

    // Setup orbit controls if enabled
    if (config.enableControls) {
      this.controls = new OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;
    }

    // Add basic lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    this.scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(10, 10, 10);
    this.scene.add(directionalLight);

    // Handle window resize
    this.handleResize = this.handleResize.bind(this);
    window.addEventListener('resize', this.handleResize);

    // Start render loop
    this.startRenderLoop();
  }

  /**
   * Add a model to the scene.
   * If the model has a parent, it will be attached to that parent's hierarchy.
   */
  addModel(config: Model3DConfig): Model3D {
    const model = new Model3D(config);
    this.models.set(config.id, model);

    // Handle parent-child relationship
    if (config.parentId) {
      const parent = this.models.get(config.parentId);
      if (parent) {
        model.setParent(parent);
      } else {
        alert(`Parent model "${config.parentId}" not found for model "${config.id}"`);
        this.scene.add(model.object3D);
      }
    } else {
      // No parent, add directly to scene
      this.scene.add(model.object3D);
    }

    return model;
  }

  /**
   * Get a model by ID
   */
  getModel(id: string): Model3D | undefined {
    return this.models.get(id);
  }

  /**
   * Remove a model from the scene
   */
  removeModel(id: string): void {
    const model = this.models.get(id);
    if (model) {
      this.scene.remove(model.object3D);
      model.dispose();
      this.models.delete(id);
    }
  }

  /**
   * Update model transforms
   */
  updateModels(transforms: Record<string, ModelTransform>): void {
    for (const [modelId, transform] of Object.entries(transforms)) {
      const model = this.models.get(modelId);
      if (model) {
        model.updateTransform(transform);
      }
    }
  }

  /**
   * Get the Three.js scene (for advanced usage)
   */
  getScene(): THREE.Scene {
    return this.scene;
  }

  /**
   * Get the Three.js camera
   */
  getCamera(): THREE.Camera {
    return this.camera;
  }

  /**
   * Get the Three.js renderer
   */
  getRenderer(): THREE.WebGLRenderer {
    return this.renderer;
  }

  /**
   * Get orbit controls if enabled
   */
  getControls(): OrbitControls | null {
    return this.controls;
  }

  /**
   * Start the render loop
   */
  private startRenderLoop(): void {
    const animate = () => {
      this.animationFrameId = requestAnimationFrame(animate);

      // Update controls
      if (this.controls) {
        this.controls.update();
      }

      // Render
      this.renderer.render(this.scene, this.camera);
    };

    animate();
  }

  /**
   * Handle window resize
   */
  private handleResize(): void {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;

    // Update camera aspect ratio
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

    // Update renderer size
    this.renderer.setSize(width, height);
  }

  /**
   * Add a custom object to the scene (e.g., helpers, additional meshes)
   * The object will be tracked and cleaned up on dispose
   */
  addObject(object: THREE.Object3D): void {
    this.scene.add(object);
    this.sceneObjects.push(object);
  }

  /**
   * Remove a custom object from the scene
   */
  removeObject(object: THREE.Object3D): void {
    this.scene.remove(object);
    const index = this.sceneObjects.indexOf(object);
    if (index > -1) {
      this.sceneObjects.splice(index, 1);
    }
  }

  /**
   * Clean up resources
   */
  dispose(): void {
    // Stop render loop
    if (this.animationFrameId !== null) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }

    // Remove event listeners
    window.removeEventListener('resize', this.handleResize);

    // Dispose controls
    if (this.controls) {
      this.controls.dispose();
      this.controls = null;
    }

    // Dispose all models
    this.models.forEach((model) => model.dispose());
    this.models.clear();

    // Remove tracked scene objects
    this.sceneObjects.forEach((obj) => this.scene.remove(obj));
    this.sceneObjects = [];

    // Dispose renderer
    this.renderer.dispose();

    // Remove canvas from DOM
    if (this.renderer.domElement.parentElement) {
      this.renderer.domElement.parentElement.removeChild(this.renderer.domElement);
    }

    // Clear scene
    this.scene.clear();
  }
}
