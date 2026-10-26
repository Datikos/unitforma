import {
  Component,
  ElementRef,
  OnDestroy,
  effect,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

export interface MassingUnitInfo {
  unit_id: string;
  code: string;
  unit_type: string;
  building_code: string;
  floor_level: number;
  /** draft | active | removed; drafts are drawn translucent (ADR-0011). */
  lifecycle_status?: string;
}

/** A public site feature drawn on the ground (ADR-0016 Decision 3), site-frame metres. */
export interface SiteFeature3D {
  kind: string;
  name?: string;
  ring_m: [number, number][];
}

/** Ground colours per feature kind; gardens also get trees. */
const FEATURE_COLOURS: Record<string, number> = {
  garden: 0x9fcf8a,
  road: 0x9ca3af,
  parking_zone: 0xb0b6bf,
  amenity: 0xa7d8f0,
  common_area: 0xe3d9c6,
  entrance: 0xf5b86b,
  other: 0xd6d3cd,
};
const GROUND_COLOUR = 0xdfe8d8;
const TREE_EVERY_M2 = 45;
const MAX_TREES = 240;

/** Opacity of a unit whose mapping is not approved yet. */
const DRAFT_OPACITY = 0.55;
const WHITE = new THREE.Color(0xffffff);
const NEUTRAL_WALL = new THREE.Color(0xd3d6dc);

/** Opacity of units outside the focused floor or building (ADR-0006 Decision 6). */
const FADE_OTHER_FLOOR = 0.18;
const FADE_OTHER_BUILDING = 0.08;

/**
 * Schematic massing viewer (plan §11.3 MVP 3D): orbit/zoom, floor isolation, unit hover and
 * pick, highlight of the selected unit. Expects the GLB produced by the worker: one mesh per
 * unit with `extras` {unit_id, code, unit_type, building_code, floor_level}.
 *
 * Floor-first navigation (ADR-0006 Decision 6): with `floorLevel` set the other floors of the
 * focused building stay visible but faded, so a buyer sees where the floor sits in the building
 * and can tap another floor to move there (`floorPicked`). With `buildingCode` set the other
 * buildings are faded further and cannot be picked, and the camera frames that building.
 */
@Component({
  selector: 'uf-massing-viewer',
  template: `
    <div class="mv" #host (pointermove)="onMove($event)" (click)="onClick($event)">
      <canvas #canvas></canvas>
      <div class="mv__badge">{{ badge() }}</div>
      @if (status(); as s) {
        <div class="mv__status">{{ s }}</div>
      }
      @if (hovered(); as h) {
        <div class="mv__hover">
          {{ h.building_code }} · {{ h.code }} · level {{ h.floor_level }}
          @if (h.lifecycle_status === 'draft') {
            · draft
          }
        </div>
      }
    </div>
  `,
  styles: `
    :host {
      display: block;
    }
    .mv {
      position: relative;
      width: 100%;
      height: var(--uf-3d-height, 70vh);
      min-height: var(--uf-3d-min-height, 420px);
      background: linear-gradient(180deg, #cfe3f7 0%, #eaf2fb 55%, #f4f6f3 100%);
      overflow: hidden;
    }
    canvas {
      display: block;
      width: 100%;
      height: 100%;
    }
    .mv__badge {
      position: absolute;
      left: 0.5rem;
      bottom: 0.5rem;
      font:
        12px system-ui,
        sans-serif;
      color: #374151;
      background: rgba(255, 255, 255, 0.85);
      padding: 0.25rem 0.5rem;
      border-radius: 4px;
    }
    .mv__status {
      position: absolute;
      left: 50%;
      top: 50%;
      transform: translate(-50%, -50%);
      font:
        14px system-ui,
        sans-serif;
      color: #374151;
    }
    .mv__hover {
      position: absolute;
      right: 0.5rem;
      top: 0.5rem;
      font:
        13px system-ui,
        sans-serif;
      background: rgba(17, 24, 39, 0.85);
      color: #fff;
      padding: 0.25rem 0.5rem;
      border-radius: 4px;
      pointer-events: none;
    }
  `,
})
export class MassingViewerComponent implements OnDestroy {
  /** Signed GLB URL. */
  readonly src = input<string | null>(null);
  /** Focus one floor level: other floors of the focused building are faded (null = all). */
  readonly floorLevel = input<number | null>(null);
  /** Focus one building: other buildings are faded and not pickable (null = all). */
  readonly buildingCode = input<string | null>(null);
  /** Disclaimer shown on the model (plan §7.3); changes with the model kind. */
  readonly badge = input<string>(
    'Schematic model generated from floor plans — not an architectural model',
  );
  /** Selected unit id (highlighted). */
  readonly selectedUnitId = input<string | null>(null);
  /** Per-unit base colours (e.g. by availability), keyed by unit id; others keep the GLB colour. */
  readonly unitColors = input<Record<string, string> | null>(null);
  /** `availability`: walls take `unitColors`, facade drawings are tinted at 45 %; `neutral`: light
   * grey walls and untinted drawings. Roofs are never tinted (ADR-0017 Decision 2). */
  readonly tintMode = input<'availability' | 'neutral'>('availability');
  /** Public site features (gardens, roads, parking, …) drawn on the ground around the model. */
  readonly siteFeatures = input<SiteFeature3D[] | null>(null);

  readonly unitPicked = output<MassingUnitInfo>();
  /** A unit on another floor than `floorLevel` was tapped: the level to move to. */
  readonly floorPicked = output<number>();
  readonly loadedUnits = output<MassingUnitInfo[]>();

  readonly status = signal<string | null>('No model loaded');
  readonly hovered = signal<MassingUnitInfo | null>(null);
  /** Bumped after each model load so colour effects re-run. */
  readonly loadedTick = signal(0);

  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private renderer: THREE.WebGLRenderer | null = null;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
  private controls: OrbitControls | null = null;
  private model: THREE.Group | null = null;
  private environment: THREE.Group | null = null;
  private sun: THREE.DirectionalLight | null = null;
  private meshes: THREE.Mesh[] = [];
  private raycaster = new THREE.Raycaster();
  private frame = 0;
  private resizeObs: ResizeObserver | null = null;
  private readonly baseColours = new Map<THREE.Mesh, THREE.Color>();
  /** The colour each mesh had in the GLB, before any tint. */
  private readonly glbColours = new Map<THREE.Mesh, THREE.Color>();
  /** IFC models arrive Draco-compressed (ADR-0006 C2a); the decoder files are copied by
   *  angular.json from three's examples into `assets/draco/` of both apps. */
  private readonly draco = new DRACOLoader().setDecoderPath('assets/draco/');
  private readonly loader = new GLTFLoader().setDRACOLoader(this.draco);

  constructor() {
    effect(() => {
      const url = this.src();
      this.ensureRenderer();
      if (url) void this.load(url);
    });
    effect(() => {
      this.floorLevel();
      this.buildingCode();
      this.loadedTick();
      this.applyFocus();
    });
    effect(() => {
      const sel = this.selectedUnitId();
      for (const m of this.meshes) this.paint(m, m.userData['unit_id'] === sel ? 'selected' : null);
    });
    effect(() => {
      this.siteFeatures();
      this.loadedTick();
      this.buildEnvironment();
    });
    effect(() => {
      this.unitColors();
      this.tintMode();
      this.loadedTick();
      this.recolour();
    });
  }

  private ensureRenderer(): void {
    if (this.renderer) return;
    const canvas = this.canvas().nativeElement;
    try {
      this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    } catch {
      this.status.set('WebGL is not available on this device');
      return;
    }
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5)); // mobile budget (plan §11.3)
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.scene.background = null; // the host paints the sky gradient behind the transparent canvas
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0xb7c4a8, 1.1));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(80, 120, 60);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.bias = -0.0005;
    this.sun = sun;
    this.scene.add(sun);
    this.scene.add(sun.target);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.02;
    this.resizeObs = new ResizeObserver(() => this.resize());
    this.resizeObs.observe(this.host().nativeElement);
    this.resize();
    const loop = () => {
      this.frame = requestAnimationFrame(loop);
      this.controls?.update();
      this.renderer?.render(this.scene, this.camera);
    };
    loop();
  }

  private resize(): void {
    if (!this.renderer) return;
    const el = this.host().nativeElement;
    const w = el.clientWidth || 1;
    const h = el.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  private async load(url: string): Promise<void> {
    if (!this.renderer) return;
    this.status.set('Loading model…');
    if (this.model) {
      this.scene.remove(this.model);
      this.model.traverse((o) => {
        if (o instanceof THREE.Mesh) {
          o.geometry.dispose();
          (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => m.dispose());
        }
      });
      this.model = null;
      this.meshes = [];
      this.baseColours.clear();
      this.glbColours.clear();
    }
    try {
      const gltf = await this.loader.loadAsync(url);
      this.model = gltf.scene;
      const infos: MassingUnitInfo[] = [];
      const seen = new Set<string>();
      this.model.traverse((o) => {
        if (o instanceof THREE.Mesh) {
          // materials are shared per unit type in the GLB; clone so highlights stay per unit
          const mat = (o.material as THREE.MeshStandardMaterial).clone();
          mat.flatShading = true;
          o.material = mat;
          o.castShadow = true;
          o.receiveShadow = true;
          // glTF material extras arrive in userData: roof | wall | facade (ADR-0017 Decision 2)
          o.userData['role'] = (mat.userData?.['role'] as string | undefined) ?? 'wall';
          this.glbColours.set(o, mat.color.clone());
          this.baseColours.set(o, mat.color.clone());
          const x = (o.userData ?? {}) as Partial<MassingUnitInfo>;
          if (x.unit_id) {
            this.meshes.push(o);
            // a unit with facade drawings is several primitives, so several meshes: one info each
            if (!seen.has(x.unit_id)) seen.add(x.unit_id);
            else return;
            infos.push({
              unit_id: x.unit_id,
              code: x.code ?? o.name,
              unit_type: x.unit_type ?? 'apartment',
              building_code: x.building_code ?? '',
              floor_level: Number(x.floor_level ?? 0),
              lifecycle_status: x.lifecycle_status,
            });
          }
        }
      });
      this.scene.add(this.model);
      this.addEdges();
      this.buildEnvironment();
      this.applyFocus();
      this.frameAll();
      this.status.set(this.meshes.length ? null : 'Model has no units yet');
      this.loadedUnits.emit(infos);
      this.loadedTick.update((n) => n + 1);
    } catch (e) {
      this.status.set(`Could not load model: ${(e as Error).message ?? e}`);
    }
  }

  /** Thin dark outlines so floors and units read even on a textured or faded facade. */
  private addEdges(): void {
    const lineMat = new THREE.LineBasicMaterial({
      color: 0x334155,
      transparent: true,
      opacity: 0.35,
    });
    for (const m of this.meshes) {
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry, 25), lineMat);
      edges.userData['edges'] = true;
      m.add(edges);
    }
  }

  /** Ground, sky light, shadow frame and the public site features around the model. */
  private buildEnvironment(): void {
    if (!this.model) return;
    if (this.environment) {
      this.scene.remove(this.environment);
      this.environment.traverse((o) => {
        if (o instanceof THREE.Mesh) {
          o.geometry.dispose();
          (Array.isArray(o.material) ? o.material : [o.material]).forEach((mm) => mm.dispose());
        }
      });
    }
    const env = new THREE.Group();
    const box = new THREE.Box3().setFromObject(this.model);
    const size = box.getSize(new THREE.Vector3());
    const groundY = Math.min(box.min.y, 0) - 0.02;
    const center = new THREE.Vector3(
      (box.min.x + box.max.x) / 2,
      groundY,
      (box.min.z + box.max.z) / 2,
    );
    const features = this.siteFeatures() ?? [];
    const featureBox = new THREE.Box2();
    for (const f of features)
      for (const [x, z] of f.ring_m) featureBox.expandByPoint(new THREE.Vector2(x, z));
    const reach = Math.max(size.x, size.z, 20) * 2.2;
    const span = features.length
      ? Math.max(
          reach,
          (featureBox.max.x - featureBox.min.x) * 1.4,
          (featureBox.max.y - featureBox.min.y) * 1.4,
        )
      : reach;
    const ground = new THREE.Mesh(
      new THREE.CircleGeometry(span, 64),
      new THREE.MeshStandardMaterial({ color: GROUND_COLOUR, roughness: 1 }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.copy(center);
    ground.receiveShadow = true;
    env.add(ground);
    let order = 1;
    for (const f of features) {
      if (f.ring_m.length < 3) continue;
      const shape = new THREE.Shape(f.ring_m.map(([x, z]) => new THREE.Vector2(x, -z)));
      const mesh = new THREE.Mesh(
        new THREE.ShapeGeometry(shape),
        new THREE.MeshStandardMaterial({
          color: FEATURE_COLOURS[f.kind] ?? FEATURE_COLOURS['other'],
          roughness: 1,
        }),
      );
      mesh.rotation.x = -Math.PI / 2;
      mesh.position.y = groundY + 0.01 * order++;
      mesh.receiveShadow = true;
      env.add(mesh);
      if (f.kind === 'garden') this.addTrees(env, f.ring_m, groundY);
    }
    if (this.sun) {
      const half = Math.max(size.x, size.z, 20) * 1.2;
      const cam = this.sun.shadow.camera;
      cam.left = -half;
      cam.right = half;
      cam.top = half;
      cam.bottom = -half;
      cam.near = 1;
      cam.far = half * 6;
      cam.updateProjectionMatrix();
      this.sun.position.set(center.x + half * 0.8, center.y + half * 1.6, center.z + half * 0.6);
      this.sun.target.position.copy(center);
    }
    this.environment = env;
    this.scene.add(env);
  }

  /** Low-poly trees on a deterministic grid inside a garden polygon (no randomness, no data invented). */
  private addTrees(env: THREE.Group, ring: [number, number][], groundY: number): void {
    const xs = ring.map((p) => p[0]);
    const zs = ring.map((p) => p[1]);
    const step = Math.sqrt(TREE_EVERY_M2);
    const trunk = new THREE.CylinderGeometry(0.18, 0.25, 1.6, 6);
    const crown = new THREE.ConeGeometry(1.6, 3.4, 7);
    const trunkMat = new THREE.MeshStandardMaterial({ color: 0x8b5e3c, roughness: 1 });
    const crownMat = new THREE.MeshStandardMaterial({ color: 0x4f9d5a, roughness: 1 });
    let count = 0;
    for (let x = Math.min(...xs) + step / 2; x < Math.max(...xs) && count < MAX_TREES; x += step) {
      for (
        let z = Math.min(...zs) + step / 2;
        z < Math.max(...zs) && count < MAX_TREES;
        z += step
      ) {
        const jitter = ((Math.round(x * 7 + z * 13) % 5) - 2) * 0.12 * step; // stable, not random
        const px = x + jitter;
        const pz = z - jitter;
        if (!pointInRing(px, pz, ring)) continue;
        const t = new THREE.Mesh(trunk, trunkMat);
        t.position.set(px, groundY + 0.8, pz);
        t.castShadow = true;
        const c = new THREE.Mesh(crown, crownMat);
        c.position.set(px, groundY + 1.6 + 1.7, pz);
        c.castShadow = true;
        env.add(t, c);
        count++;
      }
    }
  }

  /** Unit meshes of the focused building (all units when no building is focused). */
  private focused(): THREE.Mesh[] {
    const code = this.buildingCode();
    const own =
      code === null ? this.meshes : this.meshes.filter((m) => m.userData['building_code'] === code);
    return own.length ? own : this.meshes;
  }

  private applyFocus(): void {
    const lvl = this.floorLevel();
    const own = new Set(this.focused());
    for (const m of this.meshes) {
      const mat = m.material as THREE.MeshStandardMaterial;
      const focus = !own.has(m)
        ? FADE_OTHER_BUILDING
        : lvl !== null && m.userData['floor_level'] !== lvl
          ? FADE_OTHER_FLOOR
          : 1;
      const opacity = m.userData['lifecycle_status'] === 'draft' ? focus * DRAFT_OPACITY : focus;
      m.visible = true;
      mat.transparent = opacity < 1;
      mat.opacity = opacity;
      mat.depthWrite = opacity === 1;
      m.userData['pickable'] = own.has(m);
      for (const child of m.children) if (child.userData['edges']) child.visible = opacity === 1;
    }
  }

  private frameAll(): void {
    if (!this.model || !this.controls) return;
    const own = this.focused();
    const box = new THREE.Box3();
    if (own.length && this.buildingCode() !== null) for (const m of own) box.expandByObject(m);
    else box.setFromObject(this.model);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length() || 50;
    this.camera.position.set(center.x + size * 0.8, center.y + size * 0.6, center.z + size * 0.8);
    this.camera.near = size / 200;
    this.camera.far = size * 20;
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(center);
    this.controls.update();
  }

  private pick(ev: MouseEvent): THREE.Mesh | null {
    if (!this.renderer || !this.meshes.length) return null;
    const rect = this.canvas().nativeElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((ev.clientX - rect.left) / rect.width) * 2 - 1,
      -((ev.clientY - rect.top) / rect.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(ndc, this.camera);
    const hit = this.raycaster.intersectObjects(
      this.meshes.filter((m) => m.visible && m.userData['pickable'] !== false),
      false,
    )[0];
    return (hit?.object as THREE.Mesh) ?? null;
  }

  /** Base colour per mesh from the GLB colour, the tint mode and `unitColors`; then repaint. */
  private recolour(): void {
    const colours = this.unitColors();
    const neutral = this.tintMode() === 'neutral';
    const sel = this.selectedUnitId();
    for (const m of this.meshes) {
      const glb = this.glbColours.get(m);
      if (!glb) continue;
      const role = m.userData['role'] as string;
      const c = colours?.[m.userData['unit_id'] as string];
      let base = glb;
      if (role === 'roof') base = glb;
      else if (neutral) base = role === 'facade' ? WHITE : NEUTRAL_WALL;
      else if (c)
        base =
          role === 'facade' ? WHITE.clone().lerp(new THREE.Color(c), 0.45) : new THREE.Color(c);
      this.baseColours.set(m, base.clone());
      this.paint(m, m.userData['unit_id'] === sel ? 'selected' : null);
    }
  }

  private paint(m: THREE.Mesh, state: 'hover' | 'selected' | null): void {
    const mat = m.material as THREE.MeshStandardMaterial;
    const base = this.baseColours.get(m);
    if (!base) return;
    if (state === 'selected') mat.color.set(0xf59e0b);
    else if (state === 'hover') mat.color.copy(base).lerp(new THREE.Color(0x2563eb), 0.35);
    else mat.color.copy(base);
  }

  onMove(ev: PointerEvent): void {
    const m = this.pick(ev);
    const sel = this.selectedUnitId();
    for (const mesh of this.meshes)
      this.paint(mesh, mesh.userData['unit_id'] === sel ? 'selected' : mesh === m ? 'hover' : null);
    this.hovered.set(m ? (m.userData as MassingUnitInfo) : null);
  }

  onClick(ev: MouseEvent): void {
    const m = this.pick(ev);
    if (!m) return;
    const info = m.userData as MassingUnitInfo;
    const lvl = this.floorLevel();
    if (lvl !== null && info.floor_level !== lvl) this.floorPicked.emit(info.floor_level);
    this.unitPicked.emit(info);
  }

  ngOnDestroy(): void {
    cancelAnimationFrame(this.frame);
    this.resizeObs?.disconnect();
    this.controls?.dispose();
    this.renderer?.dispose();
    this.draco.dispose();
  }
}

/** Even-odd point-in-polygon on site-frame metres. */
function pointInRing(x: number, z: number, ring: [number, number][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, zi] = ring[i];
    const [xj, zj] = ring[j];
    if (zi > z !== zj > z && x < ((xj - xi) * (z - zi)) / (zj - zi) + xi) inside = !inside;
  }
  return inside;
}
