import {
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';

/** Normalised sheet coordinates: x, y in [0, 1] relative to the raster width/height. */
export type Point = [number, number];
export type Ring = Point[];

export type PlanPolygonKind = 'unit' | 'candidate' | 'ghost' | 'footprint' | 'region' | 'furniture';

export interface PlanPolygon {
  id: string;
  ring: Ring;
  label?: string;
  status?: string; // draft | approved | superseded
  selected?: boolean;
  /**
   * unit (default), candidate (dashed suggestion), ghost (previous revision), footprint (building
   * outline), region (the part of a multi-floor sheet that shows one floor; not clickable)
   */
  kind?: PlanPolygonKind;
  /** Explicit colours (e.g. availability in the buyer portal); override the kind styles. */
  fill?: string;
  stroke?: string;
  /** Not draggable in move mode (the unit outline behind the furniture ruler). */
  locked?: boolean;
  /** Accessible name announced for the polygon. */
  title?: string;
}

export type PlanMode = 'view' | 'draw' | 'calibrate' | 'move' | 'pick';

export interface PolygonMove {
  id: string;
  /** normalised delta of the drag */
  dx: number;
  dy: number;
}

/**
 * Raster plan viewer with an SVG overlay (plan §11.1 `plan-viewer`).
 * - view: pan (drag) and zoom (wheel), click a polygon to select it
 * - draw: click to add vertices, double-click or Enter to close the polygon, Escape to cancel
 * - calibrate: click two points; emits both when the second is placed
 * - move: drag a polygon; emits the normalised delta on release (placement editor)
 * - pick: every click emits a point (two-point alignment)
 * All emitted coordinates are normalised to the raster.
 */
@Component({
  selector: 'uf-plan-viewer',
  template: `
    <div
      class="pv"
      #host
      [style.--uf-plan-aspect]="width() + ' / ' + height()"
      [class.pv--draw]="mode() === 'draw' || mode() === 'calibrate' || mode() === 'pick'"
      [class.pv--move]="mode() === 'move'"
      [class.pv--has-selection]="!!selectedPolygon()"
      (wheel)="onWheel($event)"
      (pointerdown)="onPointerDown($event)"
      (pointermove)="onPointerMove($event)"
      (pointerup)="onPointerUp($event)"
      (pointerleave)="onPointerUp($event)"
      (dblclick)="onDblClick($event)"
      (keydown)="onKey($event)"
      (fullscreenchange)="onFullscreenChange()"
      tabindex="0"
    >
      <div class="pv__stage" [style.transform]="transform()">
        @if (src(); as url) {
          <img
            class="pv__img"
            [src]="url"
            [width]="width()"
            [height]="height()"
            draggable="false"
            alt="plan sheet"
            (load)="loaded.set(true)"
          />
        } @else {
          <div class="pv__blank" [style.width.px]="width()" [style.height.px]="height()"></div>
        }
        <svg
          class="pv__svg"
          [attr.viewBox]="'0 0 ' + width() + ' ' + height()"
          [attr.width]="width()"
          [attr.height]="height()"
        >
          @for (p of polygons(); track p.id) {
            <polygon
              [attr.points]="toPoints(p.ring, p.id)"
              class="pv__poly"
              [class.pv__poly--approved]="p.status === 'approved'"
              [class.pv__poly--candidate]="p.kind === 'candidate'"
              [class.pv__poly--ghost]="p.kind === 'ghost'"
              [class.pv__poly--footprint]="p.kind === 'footprint'"
              [class.pv__poly--region]="p.kind === 'region'"
              [class.pv__poly--furniture]="p.kind === 'furniture'"
              [class.pv__poly--selected]="p.selected"
              [style.fill]="p.fill ?? null"
              [style.stroke]="p.stroke ?? null"
              (click)="select(p, $event)"
              (pointerdown)="grab(p, $event)"
            >
              @if (p.title) {
                <title>{{ p.title }}</title>
              }
            </polygon>
            <text
              [attr.x]="centroid(p.ring, p.id)[0]"
              [attr.y]="centroid(p.ring, p.id)[1]"
              class="pv__label"
              [class.pv__label--selected]="p.selected"
              [attr.font-size]="labelFontSize(p)"
            >
              {{ p.label ?? '' }}
            </text>
          }
          @if (selectedPolygon(); as sp) {
            <!-- drawn after every polygon so it wins over their inline availability colours
                 (ADR-0017 Decision 1): a white halo under a dark outline -->
            <polygon [attr.points]="toPoints(sp.ring, sp.id)" class="pv__poly pv__poly--halo" />
            <polygon [attr.points]="toPoints(sp.ring, sp.id)" class="pv__poly pv__poly--outline" />
          }
          @if (draft().length) {
            <polyline [attr.points]="toPoints(draft())" class="pv__draft" />
            @for (pt of draft(); track $index) {
              <circle
                [attr.cx]="pt[0] * width()"
                [attr.cy]="pt[1] * height()"
                [attr.r]="handle()"
                class="pv__vertex"
              />
            }
          }
          @for (pt of calib(); track $index) {
            <circle
              [attr.cx]="pt[0] * width()"
              [attr.cy]="pt[1] * height()"
              [attr.r]="handle() * 1.5"
              class="pv__calib"
            />
          }
          @if (calib().length === 2) {
            <line
              [attr.x1]="calib()[0][0] * width()"
              [attr.y1]="calib()[0][1] * height()"
              [attr.x2]="calib()[1][0] * width()"
              [attr.y2]="calib()[1][1] * height()"
              class="pv__calib-line"
            />
          }
          @for (pt of marks(); track $index) {
            <circle
              [attr.cx]="pt[0] * width()"
              [attr.cy]="pt[1] * height()"
              [attr.r]="handle() * 1.5"
              class="pv__mark"
            />
          }
        </svg>
      </div>
      <div class="pv__tools" role="toolbar" aria-label="Plan view">
        <button type="button" class="pv__tool" title="Zoom in" (click)="zoomBy(1.25)">+</button>
        <button type="button" class="pv__tool" title="Zoom out" (click)="zoomBy(1 / 1.25)">
          −
        </button>
        <button type="button" class="pv__tool" title="Fit the plan" (click)="fitView()">⤢</button>
        <button
          type="button"
          class="pv__tool"
          [title]="fullscreen() ? 'Leave full screen' : 'Full screen'"
          (click)="toggleFullscreen()"
        >
          {{ fullscreen() ? '✕' : '⛶' }}
        </button>
      </div>
      @if (calloutPos(); as c) {
        <div class="pv__callout" [style.left.px]="c[0]" [style.top.px]="c[1]">
          <ng-content select="[callout]" />
        </div>
      }
    </div>
  `,
  styles: `
    :host {
      display: block;
    }
    .pv {
      position: relative;
      overflow: hidden;
      width: 100%;
      max-width: 100%;
      height: auto;
      aspect-ratio: var(--uf-plan-aspect, auto);
      max-height: var(--uf-plan-max-height, var(--uf-plan-height, 70vh));
      min-height: var(--uf-plan-min-height, 420px);
      background: #e5e7eb;
      cursor: grab;
      outline: none;
      touch-action: none;
    }
    .pv--draw {
      cursor: crosshair;
    }
    .pv--move .pv__poly {
      cursor: move;
    }
    .pv__stage {
      position: absolute;
      transform-origin: 0 0;
    }
    .pv__img {
      display: block;
      user-select: none;
      max-width: none;
      max-height: none;
    }
    .pv__svg {
      max-width: none;
      max-height: none;
    }
    .pv__blank {
      background: #fff;
    }
    .pv__tools {
      position: absolute;
      top: 0.5rem;
      right: 0.5rem;
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      z-index: 3;
    }
    .pv__tool {
      width: 2rem;
      height: 2rem;
      border: 1px solid #cbd5e1;
      border-radius: 0.4rem;
      background: rgba(255, 255, 255, 0.95);
      color: #0f172a;
      font: inherit;
      font-size: 1.05rem;
      line-height: 1;
      cursor: pointer;
      display: grid;
      place-items: center;
    }
    .pv__tool:hover {
      background: #fff;
      border-color: #94a3b8;
    }
    .pv__callout {
      position: absolute;
      z-index: 4;
      transform: translate(-50%, calc(-100% - 10px));
      pointer-events: none;
    }
    .pv__callout > * {
      pointer-events: auto;
    }
    .pv:fullscreen {
      background: #fff;
      aspect-ratio: auto;
      max-height: none;
      height: 100vh;
    }
    .pv__svg {
      position: absolute;
      left: 0;
      top: 0;
    }
    .pv__poly {
      fill: rgba(59, 130, 246, 0.18);
      stroke: #2563eb;
      stroke-width: 3;
      vector-effect: non-scaling-stroke;
      cursor: pointer;
    }
    .pv__poly--approved {
      fill: rgba(16, 185, 129, 0.18);
      stroke: #059669;
    }
    .pv__poly--candidate {
      fill: rgba(168, 85, 247, 0.12);
      stroke: #7c3aed;
      stroke-dasharray: 10 6;
    }
    .pv__poly--ghost {
      fill: none;
      stroke: #9ca3af;
      stroke-dasharray: 4 4;
      pointer-events: none;
    }
    .pv__poly--footprint {
      fill: rgba(220, 38, 38, 0.15);
      stroke: #b91c1c;
      stroke-width: 4;
    }
    .pv__poly--region {
      fill: rgba(13, 148, 136, 0.04);
      stroke: #0d9488;
      stroke-width: 4;
      stroke-dasharray: 16 8;
      pointer-events: none;
    }
    .pv__poly--furniture {
      fill: rgba(217, 119, 6, 0.28);
      stroke: #b45309;
      stroke-width: 2;
      cursor: move;
    }
    .pv__poly--selected {
      fill: rgba(245, 158, 11, 0.3);
      stroke: #d97706;
    }
    .pv__poly--halo {
      fill: none;
      stroke: #fff;
      stroke-width: 9;
      stroke-linejoin: round;
      pointer-events: none;
    }
    .pv__poly--outline {
      fill: rgba(245, 158, 11, 0.2);
      stroke: #b45309;
      stroke-width: 4;
      stroke-linejoin: round;
      pointer-events: none;
    }
    .pv--has-selection
      .pv__poly:not(.pv__poly--selected):not(.pv__poly--halo):not(.pv__poly--outline):not(
        .pv__poly--footprint
      ):not(.pv__poly--region) {
      opacity: 0.55;
    }
    .pv--has-selection .pv__label:not(.pv__label--selected) {
      opacity: 0.6;
    }
    .pv__label--selected {
      font-weight: 800;
    }
    .pv__label {
      fill: #111827;
      font-family: system-ui, sans-serif;
      font-weight: 600;
      text-anchor: middle;
      dominant-baseline: middle;
      pointer-events: none;
      paint-order: stroke;
      stroke: #fff;
      stroke-width: 0.2em; /* the halo follows the font, so a shrunk label keeps a thin one */
    }
    .pv__draft {
      fill: rgba(217, 119, 6, 0.15);
      stroke: #d97706;
      stroke-width: 3;
      stroke-dasharray: 8 6;
      vector-effect: non-scaling-stroke;
    }
    .pv__vertex {
      fill: #fff;
      stroke: #d97706;
      stroke-width: 2;
      vector-effect: non-scaling-stroke;
    }
    .pv__calib {
      fill: #dc2626;
    }
    .pv__calib-line {
      stroke: #dc2626;
      stroke-width: 3;
      vector-effect: non-scaling-stroke;
    }
    .pv__mark {
      fill: #0ea5e9;
      stroke: #fff;
      stroke-width: 2;
      vector-effect: non-scaling-stroke;
    }
  `,
})
export class PlanViewerComponent {
  readonly src = input<string | null>(null);
  /** Zoom to this ring (normalised) after load instead of fitting the whole sheet: the unit page. */
  readonly focus = input<Ring | null>(null);
  readonly width = input(1000);
  readonly height = input(700);
  readonly polygons = input<PlanPolygon[]>([]);
  /** Polygon id a callout (projected content with the `callout` attribute) is anchored to. */
  readonly callout = input<string | null>(null);
  readonly fullscreen = signal(false);
  /** Screen position of the callout anchor: the polygon's centroid under the current pan and zoom,
   * clamped inside the box; null while dragging or without a match. */
  readonly calloutPos = computed<[number, number] | null>(() => {
    const id = this.callout();
    if (!id || this.dragDelta()) return null;
    const p = this.polygons().find((x) => x.id === id);
    if (!p || p.ring.length < 3) return null;
    const [cx, cy] = this.centroid(p.ring);
    const [ox, oy] = this.offset();
    const s = this.scale();
    const el = this.host().nativeElement;
    const w = el.clientWidth || 1;
    const h = el.clientHeight || 1;
    const top = Math.min(...p.ring.map((q) => q[1] * this.height())) * s + oy;
    return [Math.min(w - 24, Math.max(24, cx * s + ox)), Math.min(h - 8, Math.max(56, top))];
  });
  /** The unit (never a footprint or region) drawn on top with the halo and outline. */
  readonly selectedPolygon = computed(
    () =>
      this.polygons().find(
        (p) => p.selected && p.kind !== 'footprint' && p.kind !== 'region' && p.kind !== 'ghost',
      ) ?? null,
  );
  readonly mode = input<PlanMode>('view');
  /** Extra markers (normalised), e.g. alignment points picked by the user. */
  readonly marks = input<Point[]>([]);

  readonly polygonDrawn = output<Ring>();
  readonly calibrationPicked = output<[Point, Point]>();
  readonly polygonSelected = output<string>();
  readonly polygonMoved = output<PolygonMove>();
  readonly pointPicked = output<Point>();

  readonly loaded = signal(false);
  readonly scale = signal(1);
  readonly offset = signal<Point>([0, 0]);
  readonly draft = signal<Ring>([]);
  readonly calib = signal<Point[]>([]);
  /** live drag of a polygon in move mode: id → normalised delta */
  readonly dragDelta = signal<{ id: string; dx: number; dy: number } | null>(null);
  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private readonly destroyRef = inject(DestroyRef);
  private dragging = false;
  private moved = false;
  private last: Point = [0, 0];
  private grabbed: string | null = null;
  private grabStart: Point = [0, 0];

  readonly transform = computed(
    () => `translate(${this.offset()[0]}px, ${this.offset()[1]}px) scale(${this.scale()})`,
  );
  readonly handle = computed(() => Math.max(3, 6 / this.scale()));
  /** Label size for the sheet (raster px); `labelFontSize` shrinks it per polygon. */
  readonly labelSize = computed(() => Math.max(12, Math.round(this.width() / 60)));

  /**
   * Font size (raster px, so it scales with the zoom) that keeps the label inside the polygon's
   * bounding box: the sheet size, or less for a narrow polygon such as a parking stall ("P-10" in a
   * 2.5 m stall). The selected label is 1.3× larger only where that still fits; its weight, halo
   * and callout carry the emphasis otherwise. Glyph width is estimated at 0.6 em (system-ui 600)
   * with 15 % left for the halo and the estimate's error.
   */
  labelFontSize(p: PlanPolygon): number {
    const cap = p.selected ? this.labelSize() * 1.3 : this.labelSize();
    const n = (p.label ?? '').length;
    if (!n || p.ring.length < 2) return cap;
    const xs = p.ring.map((q) => q[0]);
    const ys = p.ring.map((q) => q[1]);
    const bw = (Math.max(...xs) - Math.min(...xs)) * this.width();
    const bh = (Math.max(...ys) - Math.min(...ys)) * this.height();
    const fit = Math.min((0.85 * bw) / (0.6 * n), 0.8 * bh);
    return Math.max(4, Math.min(cap, Math.round(fit * 10) / 10));
  }

  constructor() {
    // fit the sheet into the viewport once its size is known
    effect(() => {
      this.width();
      this.height();
      this.focus();
      this.fit();
    });
    // the box follows the sheet's aspect ratio (--uf-plan-aspect), so refit when the layout settles or the window resizes
    afterNextRender(() => {
      if (typeof ResizeObserver === 'undefined') return;
      const ro = new ResizeObserver(() => this.fit());
      ro.observe(this.host().nativeElement);
      this.destroyRef.onDestroy(() => ro.disconnect());
    });
    effect(() => {
      if (this.mode() === 'view') {
        this.draft.set([]);
        this.calib.set([]);
      }
    });
  }

  /** Zoom around the centre of the box (the +/− buttons; the wheel zooms around the pointer). */
  zoomBy(factor: number): void {
    const el = this.host().nativeElement;
    const px = el.clientWidth / 2;
    const py = el.clientHeight / 2;
    const s0 = this.scale();
    const s1 = Math.min(20, Math.max(0.05, s0 * factor));
    const [ox, oy] = this.offset();
    this.offset.set([px - ((px - ox) * s1) / s0, py - ((py - oy) * s1) / s0]);
    this.scale.set(s1);
  }

  /** Fit the whole sheet again (or the `focus` ring): the reset button. */
  fitView(): void {
    this.fit();
  }

  toggleFullscreen(): void {
    const el = this.host().nativeElement;
    if (document.fullscreenElement === el) void document.exitFullscreen();
    else void el.requestFullscreen?.();
  }

  onFullscreenChange(): void {
    this.fullscreen.set(document.fullscreenElement === this.host().nativeElement);
    setTimeout(() => this.fit(), 50); // the box has its new size after the browser's layout pass
  }

  /** Scale the sheet to the box and centre it, or zoom onto the `focus` ring with a margin. */
  private fit(): void {
    const w = this.width();
    const h = this.height();
    const el = this.host().nativeElement;
    if (!el.clientWidth || !el.clientHeight) return;
    const ring = this.focus();
    if (ring && ring.length >= 3) {
      const xs = ring.map((p) => p[0] * w);
      const ys = ring.map((p) => p[1] * h);
      const bw = Math.max(1, Math.max(...xs) - Math.min(...xs)) * 2.2;
      const bh = Math.max(1, Math.max(...ys) - Math.min(...ys)) * 2.2;
      const s = Math.min(el.clientWidth / bw, el.clientHeight / bh, el.clientWidth / w / 0.25);
      const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
      const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
      this.scale.set(s);
      this.offset.set([el.clientWidth / 2 - cx * s, el.clientHeight / 2 - cy * s]);
      return;
    }
    const s = Math.min(el.clientWidth / w, el.clientHeight / h) * 0.95 || 1;
    this.scale.set(s);
    this.offset.set([(el.clientWidth - w * s) / 2, (el.clientHeight - h * s) / 2]);
  }

  private shifted(ring: Ring, id?: string): Ring {
    const d = this.dragDelta();
    if (!d || d.id !== id) return ring;
    return ring.map(([x, y]) => [x + d.dx, y + d.dy] as Point);
  }

  toPoints(ring: Ring, id?: string): string {
    return this.shifted(ring, id)
      .map(([x, y]) => `${x * this.width()},${y * this.height()}`)
      .join(' ');
  }

  centroid(ring: Ring, id?: string): Point {
    const r = this.shifted(ring, id);
    const n = r.length || 1;
    const cx = r.reduce((a, p) => a + p[0], 0) / n;
    const cy = r.reduce((a, p) => a + p[1], 0) / n;
    return [cx * this.width(), cy * this.height()];
  }

  select(p: PlanPolygon, ev: MouseEvent): void {
    if (this.mode() !== 'view' && this.mode() !== 'move') return;
    if (p.kind === 'ghost' || p.kind === 'region') return;
    ev.stopPropagation();
    this.polygonSelected.emit(p.id);
  }

  grab(p: PlanPolygon, ev: PointerEvent): void {
    if (this.mode() !== 'move' || p.kind === 'ghost' || p.kind === 'region' || p.locked) return;
    ev.stopPropagation();
    this.host().nativeElement.focus({ preventScroll: true }); // scrolling here would move the target between pointerdown and click
    this.grabbed = p.id;
    this.grabStart = this.toSheet(ev, false);
    this.dragDelta.set({ id: p.id, dx: 0, dy: 0 });
    this.polygonSelected.emit(p.id);
  }

  /** Viewport pixel → normalised sheet coordinate. */
  private toSheet(ev: PointerEvent | MouseEvent, clamp = true): Point {
    const rect = this.host().nativeElement.getBoundingClientRect();
    const x = (ev.clientX - rect.left - this.offset()[0]) / this.scale() / this.width();
    const y = (ev.clientY - rect.top - this.offset()[1]) / this.scale() / this.height();
    return clamp ? [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))] : [x, y];
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
    this.host().nativeElement.focus({ preventScroll: true }); // scrolling here would move the target between pointerdown and click
    if (this.grabbed) return;
    this.dragging = true;
    this.moved = false;
    this.last = [ev.clientX, ev.clientY];
  }

  onPointerMove(ev: PointerEvent): void {
    if (this.grabbed) {
      const now = this.toSheet(ev, false);
      this.dragDelta.set({
        id: this.grabbed,
        dx: now[0] - this.grabStart[0],
        dy: now[1] - this.grabStart[1],
      });
      return;
    }
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
    if (this.grabbed) {
      const d = this.dragDelta();
      this.grabbed = null;
      this.dragDelta.set(null);
      if (d && (Math.abs(d.dx) > 1e-4 || Math.abs(d.dy) > 1e-4)) this.polygonMoved.emit(d);
      return;
    }
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
    } else if (this.mode() === 'pick') {
      this.pointPicked.emit(pt);
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
    const cleaned = ring.filter(
      (p, i) => i === 0 || p[0] !== ring[i - 1][0] || p[1] !== ring[i - 1][1],
    );
    if (cleaned.length >= 3) this.polygonDrawn.emit(cleaned);
    this.draft.set([]);
  }

  resetCalibration(): void {
    this.calib.set([]);
  }
}
