import { Component, ElementRef, OnDestroy, effect, input, output, signal, viewChild } from '@angular/core';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

export interface MassingUnitInfo {
  unit_id: string;
  code: string;
  unit_type: string;
  building_code: string;
  floor_level: number;
}

/**
 * Schematic massing viewer (plan §11.3 MVP 3D): orbit/zoom, floor isolation, unit hover and
 * pick, highlight of the selected unit. Expects the GLB produced by the worker: one mesh per
 * unit with `extras` {unit_id, code, unit_type, building_code, floor_level}.
 */
@Component({
  selector: 'uf-massing-viewer',
  template: `
    <div class="mv" #host (pointermove)="onMove($event)" (click)="onClick($event)">
      <canvas #canvas></canvas>
      <div class="mv__badge">Schematic model generated from floor plans — not an architectural model</div>
      @if (status(); as s) { <div class="mv__status">{{ s }}</div> }
      @if (hovered(); as h) { <div class="mv__hover">{{ h.building_code }} · {{ h.code }} · level {{ h.floor_level }}</div> }
    </div>
  `,
  styles: `
    :host { display: block; }
    .mv { position: relative; width: 100%; height: var(--uf-3d-height, 70vh); min-height: var(--uf-3d-min-height, 420px); background: #f3f4f6; overflow: hidden; }
    canvas { display: block; width: 100%; height: 100%; }
    .mv__badge { position: absolute; left: 0.5rem; bottom: 0.5rem; font: 12px system-ui, sans-serif; color: #374151; background: rgba(255,255,255,0.85); padding: 0.25rem 0.5rem; border-radius: 4px; }
    .mv__status { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); font: 14px system-ui, sans-serif; color: #374151; }
    .mv__hover { position: absolute; right: 0.5rem; top: 0.5rem; font: 13px system-ui, sans-serif; background: rgba(17,24,39,0.85); color: #fff; padding: 0.25rem 0.5rem; border-radius: 4px; pointer-events: none; }
  `,
})
export class MassingViewerComponent implements OnDestroy {
  /** Signed GLB URL. */
  readonly src = input<string | null>(null);
  /** Only show units on this floor level (null = all). */
  readonly floorLevel = input<number | null>(null);
  /** Selected unit id (highlighted). */
  readonly selectedUnitId = input<string | null>(null);
  /** Per-unit base colours (e.g. by availability), keyed by unit id; others keep the GLB colour. */
  readonly unitColors = input<Record<string, string> | null>(null);

  readonly unitPicked = output<MassingUnitInfo>();
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
  private meshes: THREE.Mesh[] = [];
  private raycaster = new THREE.Raycaster();
  private frame = 0;
  private resizeObs: ResizeObserver | null = null;
  private readonly baseColours = new Map<THREE.Mesh, THREE.Color>();

  constructor() {
    effect(() => {
      const url = this.src();
      this.ensureRenderer();
      if (url) void this.load(url);
    });
    effect(() => {
      const lvl = this.floorLevel();
      for (const m of this.meshes) m.visible = lvl === null || m.userData['floor_level'] === lvl;
    });
    effect(() => {
      const sel = this.selectedUnitId();
      for (const m of this.meshes) this.paint(m, m.userData['unit_id'] === sel ? 'selected' : null);
    });
    effect(() => {
      const colours = this.unitColors();
      this.loadedTick();
      if (!colours) return;
      for (const m of this.meshes) {
        const c = colours[m.userData['unit_id'] as string];
        if (c) this.baseColours.set(m, new THREE.Color(c));
        this.paint(m, m.userData['unit_id'] === this.selectedUnitId() ? 'selected' : null);
      }
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
    this.scene.background = new THREE.Color(0xf3f4f6);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x9ca3af, 1.2));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(80, 120, 60);
    this.scene.add(sun);
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
    }
    try {
      const gltf = await new GLTFLoader().loadAsync(url);
      this.model = gltf.scene;
      const infos: MassingUnitInfo[] = [];
      this.model.traverse((o) => {
        if (o instanceof THREE.Mesh) {
          // materials are shared per unit type in the GLB; clone so highlights stay per unit
          const mat = (o.material as THREE.MeshStandardMaterial).clone();
          mat.flatShading = true;
          o.material = mat;
          this.baseColours.set(o, mat.color.clone());
          const x = (o.userData ?? {}) as Partial<MassingUnitInfo>;
          if (x.unit_id) {
            this.meshes.push(o);
            infos.push({ unit_id: x.unit_id, code: x.code ?? o.name, unit_type: x.unit_type ?? 'apartment', building_code: x.building_code ?? '', floor_level: Number(x.floor_level ?? 0) });
          }
        }
      });
      this.scene.add(this.model);
      this.addGround();
      this.frameAll();
      this.status.set(this.meshes.length ? null : 'Model has no units yet');
      this.loadedUnits.emit(infos);
      this.loadedTick.update((n) => n + 1);
      const lvl = this.floorLevel();
      for (const m of this.meshes) m.visible = lvl === null || m.userData['floor_level'] === lvl;
    } catch (e) {
      this.status.set(`Could not load model: ${(e as Error).message ?? e}`);
    }
  }

  private addGround(): void {
    const box = new THREE.Box3().setFromObject(this.model!);
    const size = box.getSize(new THREE.Vector3());
    const span = Math.max(size.x, size.z, 20) * 1.5;
    const grid = new THREE.GridHelper(span, Math.round(span / 5), 0xd1d5db, 0xe5e7eb);
    grid.position.set((box.min.x + box.max.x) / 2, Math.min(box.min.y, 0) - 0.01, (box.min.z + box.max.z) / 2);
    this.model!.add(grid);
  }

  private frameAll(): void {
    if (!this.model || !this.controls) return;
    const box = new THREE.Box3().setFromObject(this.model);
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
    const ndc = new THREE.Vector2(((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    const hit = this.raycaster.intersectObjects(this.meshes.filter((m) => m.visible), false)[0];
    return (hit?.object as THREE.Mesh) ?? null;
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
    for (const mesh of this.meshes) this.paint(mesh, mesh.userData['unit_id'] === sel ? 'selected' : mesh === m ? 'hover' : null);
    this.hovered.set(m ? (m.userData as MassingUnitInfo) : null);
  }

  onClick(ev: MouseEvent): void {
    const m = this.pick(ev);
    if (m) this.unitPicked.emit(m.userData as MassingUnitInfo);
  }

  ngOnDestroy(): void {
    cancelAnimationFrame(this.frame);
    this.resizeObs?.disconnect();
    this.controls?.dispose();
    this.renderer?.dispose();
  }
}
