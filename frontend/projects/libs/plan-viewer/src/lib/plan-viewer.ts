import { Component, ElementRef, computed, effect, input, output, signal, viewChild } from '@angular/core';

/** Normalised sheet coordinates: x, y in [0, 1] relative to the raster width/height. */
export type Point = [number, number];
export type Ring = Point[];

export interface PlanPolygon {
  id: string;
  ring: Ring;
  label?: string;
  status?: string; // draft | approved | superseded
  selected?: boolean;
}

export type PlanMode = 'view' | 'draw' | 'calibrate';

/**
 * Raster plan viewer with an SVG overlay (plan §11.1 `plan-viewer`).
 * - view: pan (drag) and zoom (wheel), click a polygon to select it
 * - draw: click to add vertices, double-click or Enter to close the polygon, Escape to cancel
 * - calibrate: click two points; emits both when the second is placed
 * All emitted coordinates are normalised to the raster.
 */
@Component({
  selector: 'uf-plan-viewer',
  template: `
    <div
      class="pv"
      #host
      [class.pv--draw]="mode() !== 'view'"
      (wheel)="onWheel($event)"
      (pointerdown)="onPointerDown($event)"
      (pointermove)="onPointerMove($event)"
      (pointerup)="onPointerUp($event)"
      (pointerleave)="onPointerUp($event)"
      (dblclick)="onDblClick($event)"
      (keydown)="onKey($event)"
      tabindex="0"
    >
      <div class="pv__stage" [style.transform]="transform()">
        @if (src(); as url) {
          <img class="pv__img" [src]="url" [width]="width()" [height]="height()" draggable="false" alt="plan sheet" (load)="loaded.set(true)" />
        }
        <svg class="pv__svg" [attr.viewBox]="'0 0 ' + width() + ' ' + height()" [attr.width]="width()" [attr.height]="height()">
          @for (p of polygons(); track p.id) {
            <polygon
              [attr.points]="toPoints(p.ring)"
              class="pv__poly"
              [class.pv__poly--approved]="p.status === 'approved'"
              [class.pv__poly--selected]="p.selected"
              (click)="select(p, $event)"
            />
            <text [attr.x]="centroid(p.ring)[0]" [attr.y]="centroid(p.ring)[1]" class="pv__label" [attr.font-size]="labelSize()">{{ p.label ?? '' }}</text>
          }
          @if (draft().length) {
            <polyline [attr.points]="toPoints(draft())" class="pv__draft" />
            @for (pt of draft(); track $index) {
              <circle [attr.cx]="pt[0] * width()" [attr.cy]="pt[1] * height()" [attr.r]="handle()" class="pv__vertex" />
            }
          }
          @for (pt of calib(); track $index) {
            <circle [attr.cx]="pt[0] * width()" [attr.cy]="pt[1] * height()" [attr.r]="handle() * 1.5" class="pv__calib" />
          }
          @if (calib().length === 2) {
            <line [attr.x1]="calib()[0][0] * width()" [attr.y1]="calib()[0][1] * height()" [attr.x2]="calib()[1][0] * width()" [attr.y2]="calib()[1][1] * height()" class="pv__calib-line" />
          }
        </svg>
      </div>
    </div>
  `,
  styles: `
    :host { display: block; }
    .pv { position: relative; overflow: hidden; width: 100%; height: 70vh; min-height: 420px; background: #e5e7eb; cursor: grab; outline: none; touch-action: none; }
    .pv--draw { cursor: crosshair; }
    .pv__stage { position: absolute; transform-origin: 0 0; }
    .pv__img { display: block; user-select: none; }
    .pv__svg { position: absolute; left: 0; top: 0; }
    .pv__poly { fill: rgba(59, 130, 246, 0.18); stroke: #2563eb; stroke-width: 3; vector-effect: non-scaling-stroke; cursor: pointer; }
    .pv__poly--approved { fill: rgba(16, 185, 129, 0.18); stroke: #059669; }
    .pv__poly--selected { fill: rgba(245, 158, 11, 0.3); stroke: #d97706; }
    .pv__label { fill: #111827; font-family: system-ui, sans-serif; font-weight: 600; text-anchor: middle; dominant-baseline: middle; pointer-events: none; paint-order: stroke; stroke: #fff; stroke-width: 4; }
    .pv__draft { fill: rgba(217, 119, 6, 0.15); stroke: #d97706; stroke-width: 3; stroke-dasharray: 8 6; vector-effect: non-scaling-stroke; }
    .pv__vertex { fill: #fff; stroke: #d97706; stroke-width: 2; vector-effect: non-scaling-stroke; }
    .pv__calib { fill: #dc2626; }
    .pv__calib-line { stroke: #dc2626; stroke-width: 3; vector-effect: non-scaling-stroke; }
  `,
})
export class PlanViewerComponent {
  readonly src = input<string | null>(null);
  readonly width = input(1000);
  readonly height = input(700);
  readonly polygons = input<PlanPolygon[]>([]);
  readonly mode = input<PlanMode>('view');

  readonly polygonDrawn = output<Ring>();
  readonly calibrationPicked = output<[Point, Point]>();
  readonly polygonSelected = output<string>();

  readonly loaded = signal(false);
  readonly scale = signal(1);
  readonly offset = signal<Point>([0, 0]);
  readonly draft = signal<Ring>([]);
  readonly calib = signal<Point[]>([]);
  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private dragging = false;
  private moved = false;
  private last: Point = [0, 0];

  readonly transform = computed(() => `translate(${this.offset()[0]}px, ${this.offset()[1]}px) scale(${this.scale()})`);
  readonly handle = computed(() => Math.max(3, 6 / this.scale()));
  readonly labelSize = computed(() => Math.max(12, Math.round(this.width() / 60)));

  constructor() {
    // fit the sheet into the viewport once its size is known
    effect(() => {
      const w = this.width();
      const h = this.height();
      const el = this.host().nativeElement;
      const s = Math.min(el.clientWidth / w, el.clientHeight / h) * 0.95 || 1;
      this.scale.set(s);
      this.offset.set([(el.clientWidth - w * s) / 2, (el.clientHeight - h * s) / 2]);
    });
    effect(() => {
      if (this.mode() === 'view') {
        this.draft.set([]);
        this.calib.set([]);
      }
    });
  }

  toPoints(ring: Ring): string {
    return ring.map(([x, y]) => `${x * this.width()},${y * this.height()}`).join(' ');
  }

  centroid(ring: Ring): Point {
    const n = ring.length || 1;
    const cx = ring.reduce((a, p) => a + p[0], 0) / n;
    const cy = ring.reduce((a, p) => a + p[1], 0) / n;
    return [cx * this.width(), cy * this.height()];
  }

  select(p: PlanPolygon, ev: MouseEvent): void {
    if (this.mode() !== 'view') return;
    ev.stopPropagation();
    this.polygonSelected.emit(p.id);
  }

  /** Viewport pixel → normalised sheet coordinate. */
  private toSheet(ev: PointerEvent | MouseEvent): Point {
    const rect = this.host().nativeElement.getBoundingClientRect();
    const x = (ev.clientX - rect.left - this.offset()[0]) / this.scale() / this.width();
    const y = (ev.clientY - rect.top - this.offset()[1]) / this.scale() / this.height();
    return [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))];
  }

  onWheel(ev: WheelEvent): void {
    ev.preventDefault();
    const factor = ev.deltaY < 0 ? 1.15 : 1 / 1.15;
    const rect = this.host().nativeElement.getBoundingClientRect();
    const px = ev.clientX - rect.left;
    const py = ev.clientY - rect.top;
    const s0 = this.scale();
    const s1 = Math.min(20, Math.max(0.05, s0 * factor));
    const [ox, oy] = this.offset();
    this.offset.set([px - ((px - ox) * s1) / s0, py - ((py - oy) * s1) / s0]);
    this.scale.set(s1);
  }

  onPointerDown(ev: PointerEvent): void {
    this.host().nativeElement.focus();
    this.dragging = true;
    this.moved = false;
    this.last = [ev.clientX, ev.clientY];
  }

  onPointerMove(ev: PointerEvent): void {
    if (!this.dragging) return;
    const dx = ev.clientX - this.last[0];
    const dy = ev.clientY - this.last[1];
    if (Math.abs(dx) + Math.abs(dy) > 2) this.moved = true;
    if (this.moved) {
      this.offset.update(([x, y]) => [x + dx, y + dy]);
      this.last = [ev.clientX, ev.clientY];
    }
  }

  onPointerUp(ev: PointerEvent): void {
    if (!this.dragging) return;
    this.dragging = false;
    if (this.moved || ev.type === 'pointerleave') return;
    const pt = this.toSheet(ev);
    if (this.mode() === 'draw') {
      this.draft.update((d) => [...d, pt]);
    } else if (this.mode() === 'calibrate') {
      const next = [...this.calib(), pt].slice(-2);
      this.calib.set(next);
      if (next.length === 2) this.calibrationPicked.emit([next[0], next[1]]);
    }
  }

  onDblClick(ev: MouseEvent): void {
    ev.preventDefault();
    this.finishPolygon();
  }

  onKey(ev: KeyboardEvent): void {
    if (ev.key === 'Enter') this.finishPolygon();
    if (ev.key === 'Escape') {
      this.draft.set([]);
      this.calib.set([]);
    }
    if (ev.key === 'Backspace' && this.mode() === 'draw') this.draft.update((d) => d.slice(0, -1));
  }

  finishPolygon(): void {
    const ring = this.draft();
    // a double-click adds the last vertex twice; drop the duplicate
    const cleaned = ring.filter((p, i) => i === 0 || p[0] !== ring[i - 1][0] || p[1] !== ring[i - 1][1]);
    if (cleaned.length >= 3) this.polygonDrawn.emit(cleaned);
    this.draft.set([]);
  }

  resetCalibration(): void {
    this.calib.set([]);
  }
}
