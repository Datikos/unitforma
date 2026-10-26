import { Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  lucideBaby,
  lucideCircle,
  lucideCookingPot,
  lucideDoorClosed,
  lucideDroplet,
  lucideEraser,
  lucideFlipHorizontal,
  lucideGrid2x2,
  lucideLamp,
  lucideLibrary,
  lucidePackage,
  lucidePalette,
  lucidePiano,
  lucideRefrigerator,
  lucideSave,
  lucideShare2,
  lucideShowerHead,
  lucideSprout,
  lucideSquare,
  lucideSun,
  lucideTable2,
  lucideToilet,
  lucideTv,
  lucideUmbrella,
  lucideWashingMachine,
} from '@ng-icons/lucide';
import { UF_ICONS } from 'ui';
import { PlanPolygon, PlanViewerComponent, PolygonMove } from 'plan-viewer';
import { PortalApi, UnitDoc } from '../core/portal-api';
import {
  CATALOGUE,
  CatalogueItem,
  Layout,
  MAX_PIECES,
  PlacedPiece,
  ROOMS,
  Room,
  RoomKey,
  Rotation,
  catalogueItem,
  countByRoom,
  encodeLayout,
  layoutFromFragment,
  layoutKey,
  loadLayout,
  outlineCentre,
  pieceLabel,
  pieceRing,
  pieceSize,
  planFrame,
  saveLayout,
  swatch,
} from './playground.model';

/**
 * Icons only this editor uses, registered here and not in `UF_ICONS` (ADR-0009 Decision 5), so the
 * admin's initial bundle does not carry them: they weighed 22 kB raw there on 2026-10-26.
 */
const PLAYGROUND_ICONS = {
  lucideBaby,
  lucideCircle,
  lucideCookingPot,
  lucideDoorClosed,
  lucideDroplet,
  lucideEraser,
  lucideFlipHorizontal,
  lucideGrid2x2,
  lucideLamp,
  lucideLibrary,
  lucidePackage,
  lucidePalette,
  lucidePiano,
  lucideRefrigerator,
  lucideSave,
  lucideShare2,
  lucideShowerHead,
  lucideSprout,
  lucideSquare,
  lucideSun,
  lucideTable2,
  lucideToilet,
  lucideTv,
  lucideUmbrella,
  lucideWashingMachine,
};

/** A placed piece with the id the viewer tracks it by. */
interface Piece extends PlacedPiece {
  id: string;
}

/**
 * The renovation playground's editor (ADR-0020 Phase A): the apartment plan as a canvas beside a tool
 * panel. The buyer places true-scale pieces from a catalogue grouped by room, drags, turns, flips and
 * removes them, fades the drawn furniture, tries a wall colour, keeps it all in this browser and shares
 * it as a link. Nothing reaches the server. Lives on `playground.page.ts`, opened in its own window.
 */
@Component({
  selector: 'uf-unit-playground',
  imports: [NgIcon, PlanViewerComponent],
  viewProviders: [provideIcons({ ...UF_ICONS, ...PLAYGROUND_ICONS })],
  host: { '(keydown)': 'onKey($event)' },
  template: `
    @if (unit().plan; as plan) {
      <div class="pe__canvas">
        <uf-plan-viewer
          [src]="api.asset(plan.url)"
          [width]="plan.width"
          [height]="plan.height"
          [polygons]="polygons()"
          [focus]="plan.ring"
          [focusPadding]="1.15"
          [clip]="plan.ring"
          [mode]="pieces().length ? 'move' : 'view'"
          (polygonMoved)="onMoved($event)"
          (polygonSelected)="onSelected($event)"
        />
        @if (shared()) {
          <p class="uf-indicative pe__shared">
            <ng-icon name="lucideShare2" /> A shared arrangement with {{ pieces().length }} pieces.
            Your own saved one is untouched until you change something; the first change saves this
            one as yours.
            @if (own()) {
              <button type="button" class="pe__link" (click)="restoreOwn()">Back to mine</button>
            }
          </p>
        }
        <p class="uf-hint pe__hint">
          <ng-icon name="lucideMaximize2" /> Only {{ unit().code }} is shown; the neighbours are
          covered. Scroll to zoom, drag the plan to pan, drag a piece to move it; tap a piece to
          select it, then R turns, F flips, Delete removes.
        </p>
      </div>
      <aside class="pe__panel" aria-label="Tools">
        @if (!frame()) {
          <p class="uf-indicative">
            <ng-icon name="lucideRuler" /> Furniture at true scale needs a stated area; this unit
            has none yet, so only the plan is shown.
          </p>
        } @else {
          <section class="pe__sec">
            <h2 class="pe__h">
              <ng-icon name="lucideLayoutGrid" /> Catalogue
              <span class="uf-muted pe__sub">true to scale</span>
            </h2>
            <div class="pe__rooms" role="tablist" aria-label="Rooms">
              @for (r of rooms; track r.key) {
                <button
                  type="button"
                  role="tab"
                  class="uf-chip-btn"
                  [attr.aria-selected]="room() === r.key"
                  [attr.aria-pressed]="room() === r.key"
                  (click)="room.set(r.key)"
                >
                  <ng-icon [name]="r.icon" aria-hidden="true" /> {{ r.label }}
                  @if (counts()[r.key]; as n) {
                    <span class="pe__count" [title]="n + ' placed'">{{ n }}</span>
                  }
                </button>
              }
            </div>
            <div class="pe__list" role="tabpanel">
              @for (f of items(); track f.id) {
                <button
                  type="button"
                  class="pe__row"
                  [title]="'Put ' + pieceLabel(f) + ' on the plan'"
                  [disabled]="pieces().length >= max"
                  (click)="add(f)"
                >
                  <ng-icon [name]="f.icon" aria-hidden="true" />
                  <span class="pe__name">{{ f.name }}</span>
                  <span class="pe__size">{{ pieceSize(f) }}</span>
                  <ng-icon name="lucidePlus" class="pe__add" aria-hidden="true" />
                </button>
              }
            </div>
          </section>
          <section class="pe__sec">
            <h2 class="pe__h">
              <ng-icon name="lucideMove" /> On the plan
              <span class="uf-muted pe__sub">{{ pieces().length }} of {{ max }}</span>
              @if (pieces().length) {
                <button
                  type="button"
                  class="pe__link pe__right"
                  title="Remove every piece you placed"
                  (click)="clear()"
                >
                  Clear all
                </button>
              }
            </h2>
            @if (!pieces().length) {
              <p class="uf-muted small">Nothing placed yet. Pick a room above and tap a piece.</p>
            }
            <div class="pe__list">
              @for (p of pieces(); track p.id) {
                <div
                  class="pe__row pe__placed"
                  [class.is-selected]="p.id === selectedId()"
                  role="button"
                  tabindex="0"
                  [attr.aria-pressed]="p.id === selectedId()"
                  (click)="select(p.id)"
                  (keydown.enter)="select(p.id)"
                >
                  <ng-icon [name]="icon(p)" aria-hidden="true" />
                  <span class="pe__name">{{ name(p) }}</span>
                  <span class="pe__size">{{ size(p) }}</span>
                  <span class="pe__tools">
                    <button
                      type="button"
                      class="pe__tool"
                      title="Turn by 90° (R)"
                      aria-label="Turn"
                      (click)="select(p.id); rotate(); $event.stopPropagation()"
                    >
                      <ng-icon name="lucideRotateCw" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      class="pe__tool"
                      title="Mirror (F)"
                      aria-label="Flip"
                      (click)="select(p.id); flip(); $event.stopPropagation()"
                    >
                      <ng-icon name="lucideFlipHorizontal" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      class="pe__tool"
                      title="Remove (Delete)"
                      aria-label="Remove"
                      (click)="select(p.id); remove(); $event.stopPropagation()"
                    >
                      <ng-icon name="lucideX" aria-hidden="true" />
                    </button>
                  </span>
                </div>
              }
            </div>
          </section>
          <section class="pe__sec">
            <h2 class="pe__h"><ng-icon name="lucidePalette" /> Finish</h2>
            <div class="pe__actions">
              <button
                type="button"
                class="uf-chip-btn"
                title="Fade the furniture drawn by the architect so your pieces stand out"
                [attr.aria-pressed]="fade()"
                (click)="fade.set(!fade())"
              >
                <ng-icon name="lucideEraser" aria-hidden="true" /> Empty the apartment
              </button>
              <label class="uf-chip-btn pe__colour" title="Try a wall colour on the plan">
                <ng-icon name="lucidePalette" aria-hidden="true" /> Walls
                <input
                  type="color"
                  [value]="wallHex()"
                  (input)="setWall($event)"
                  aria-label="Wall colour to try"
                />
                @if (wall()) {
                  <button
                    type="button"
                    class="pe__reset"
                    title="Back to the colour the developer stated"
                    aria-label="Back to the stated wall colour"
                    (click)="setWall(null)"
                  >
                    <ng-icon name="lucideX" aria-hidden="true" />
                  </button>
                }
              </label>
            </div>
            @if (unit().wall_colour; as stated) {
              <p class="uf-muted small">
                Stated by the developer: {{ stated
                }}{{ wall() ? '; you are trying ' + wall() : '' }}.
              </p>
            }
          </section>
          <section class="pe__sec">
            <h2 class="pe__h"><ng-icon name="lucideShare2" /> Share</h2>
            <div class="pe__actions">
              <button
                type="button"
                class="uf-btn"
                title="Copy a link that opens this plan with your arrangement"
                [disabled]="!pieces().length && !wall()"
                (click)="share()"
              >
                <ng-icon name="lucideShare2" aria-hidden="true" /> Share this arrangement
              </button>
            </div>
            @if (shareUrl(); as url) {
              <input
                class="pe__url"
                type="text"
                readonly
                [value]="url"
                aria-label="Share link"
                (focus)="selectAll($event)"
              />
            }
            <p class="uf-muted small">
              Whoever opens the link sees your pieces and your wall colour; nothing is sent to the
              developer.
            </p>
          </section>
          @if (status(); as st) {
            <p class="uf-muted small pe__status" aria-live="polite">
              <ng-icon [name]="st.icon" aria-hidden="true" /> {{ st.text }}
            </p>
          }
        }
      </aside>
    }
  `,
  styles: `
    :host {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(300px, 360px);
      gap: 0.75rem;
      align-items: start;
    }
    @media (max-width: 900px) {
      :host {
        grid-template-columns: 1fr;
      }
    }
    .pe__canvas {
      display: grid;
      gap: 0.35rem;
      position: sticky;
      top: 4rem;
    }
    uf-plan-viewer {
      --uf-plan-max-height: calc(100vh - 11rem);
      min-height: 420px;
      border-radius: var(--uf-radius);
      overflow: hidden;
    }
    @media (max-width: 900px) {
      .pe__canvas {
        position: static;
      }
      uf-plan-viewer {
        --uf-plan-max-height: 55vh;
        min-height: 300px;
      }
    }
    .pe__panel {
      display: grid;
      gap: 0.6rem;
      max-height: calc(100vh - 6rem);
      overflow: auto;
    }
    @media (max-width: 900px) {
      .pe__panel {
        max-height: none;
      }
    }
    .pe__sec {
      background: var(--uf-surface);
      border: 1px solid var(--uf-border);
      border-radius: var(--uf-radius);
      padding: 0.6rem 0.7rem;
      display: grid;
      gap: 0.5rem;
    }
    .pe__h {
      margin: 0;
      font-size: 0.95rem;
      display: flex;
      align-items: center;
      gap: 0.4rem;
    }
    .pe__sub {
      font-weight: 400;
      font-size: 0.8rem;
    }
    .pe__right {
      margin-left: auto;
    }
    .pe__rooms,
    .pe__actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
    }
    .pe__list {
      display: grid;
      gap: 0.2rem;
      max-height: 15rem;
      overflow: auto;
    }
    .pe__row {
      display: grid;
      grid-template-columns: auto 1fr auto auto;
      align-items: center;
      gap: 0.5rem;
      padding: 0.3rem 0.45rem;
      border: 1px solid transparent;
      border-radius: var(--uf-radius-sm);
      background: none;
      color: inherit;
      font: inherit;
      text-align: left;
      cursor: pointer;
    }
    .pe__row:hover {
      background: color-mix(in srgb, var(--uf-primary) 8%, transparent);
    }
    .pe__row.is-selected {
      border-color: #d97706;
      background: rgba(245, 158, 11, 0.14);
    }
    .pe__row > ng-icon {
      font-size: 1.15rem;
    }
    .pe__size {
      color: var(--uf-muted);
      font-size: 0.85rem;
      font-variant-numeric: tabular-nums;
    }
    .pe__add {
      color: var(--uf-primary);
    }
    .pe__tools {
      display: inline-flex;
      gap: 0.1rem;
    }
    .pe__tool,
    .pe__reset,
    .pe__link {
      border: 0;
      background: none;
      color: inherit;
      font: inherit;
      cursor: pointer;
      padding: 0.15rem;
      display: inline-flex;
      border-radius: 4px;
    }
    .pe__tool:hover {
      background: color-mix(in srgb, currentColor 12%, transparent);
    }
    .pe__link {
      text-decoration: underline;
      font-size: 0.85rem;
    }
    .pe__count {
      min-width: 1.3em;
      padding: 0 0.35em;
      border-radius: 999px;
      background: color-mix(in srgb, currentColor 18%, transparent);
      font-size: 0.78em;
      font-weight: 600;
      text-align: center;
    }
    .pe__colour {
      cursor: pointer;
    }
    .pe__colour input {
      width: 1.6rem;
      height: 1.2rem;
      padding: 0;
      border: 1px solid var(--uf-border);
      border-radius: 4px;
      background: none;
      cursor: pointer;
    }
    .pe__url {
      width: 100%;
      font: inherit;
      font-size: 0.85rem;
      padding: 0.3rem 0.5rem;
      border: 1px solid var(--uf-border);
      border-radius: var(--uf-radius-sm);
    }
    .pe__hint ng-icon,
    .pe__status ng-icon {
      vertical-align: -0.15em;
    }
    p {
      margin: 0;
    }
    .small {
      font-size: 0.85rem;
    }
  `,
})
export class UnitPlaygroundComponent {
  protected readonly api = inject(PortalApi);
  private readonly route = inject(ActivatedRoute);
  readonly unit = input.required<UnitDoc>();
  readonly slug = input.required<string>();

  protected readonly rooms: readonly Room[] = ROOMS;
  protected readonly max = MAX_PIECES;
  protected readonly pieceLabel = pieceLabel;
  protected readonly pieceSize = pieceSize;

  readonly pieces = signal<Piece[]>([]);
  readonly selectedId = signal<string | null>(null);
  readonly room = signal<RoomKey>('living');
  readonly fade = signal(false);
  /** The buyer's wall colour as hex; null shows the stated one. */
  readonly wall = signal<string | null>(null);
  /** The arrangement on screen came from a link and is not saved yet. */
  readonly shared = signal(false);
  /** The buyer's own saved arrangement, kept while a shared one is shown. */
  readonly own = signal<Layout | null>(null);
  readonly status = signal<{ icon: string; text: string } | null>(null);
  readonly shareUrl = signal<string | null>(null);
  private seq = 0;
  private loadedFor: string | null = null;
  private statusTimer: ReturnType<typeof setTimeout> | null = null;

  readonly frame = computed(() => planFrame(this.unit().plan, this.unit().areas));
  readonly items = computed(() => CATALOGUE.filter((c) => c.room === this.room()));
  readonly counts = computed(() => countByRoom(this.pieces()));
  readonly selected = computed(() => this.pieces().find((p) => p.id === this.selectedId()) ?? null);
  /** The stated colour as hex for the colour input, the primary colour when none is stated. */
  readonly wallHex = computed(() => {
    const w = this.wall();
    if (w) return w;
    const stated = this.unit().wall_colour ? swatch(this.unit().wall_colour!) : 'transparent';
    return stated === 'transparent' ? '#f1f0ea' : stated;
  });
  readonly polygons = computed<PlanPolygon[]>(() => {
    const u = this.unit();
    const f = this.frame();
    if (!u.plan?.ring) return [];
    const tint = this.wall() ?? 'var(--uf-primary)';
    const fill = this.fade()
      ? `color-mix(in srgb, color-mix(in srgb, ${tint} 12%, var(--uf-surface)) 85%, transparent)`
      : `color-mix(in srgb, ${tint} 28%, transparent)`;
    const unit: PlanPolygon = {
      id: u.unit_id,
      ring: u.plan.ring,
      label: '',
      fill,
      stroke: this.wall() ?? 'var(--uf-primary)',
      title: u.code,
      locked: true,
    };
    if (!f) return [unit];
    const sel = this.selectedId();
    return [
      unit,
      ...this.pieces().map((p) => ({
        id: p.id,
        ring: pieceRing(p, f),
        // the name alone stays readable inside a 45 cm chair; the size is in the tooltip and the toolbar
        label: catalogueItem(p.item)?.name ?? p.item,
        kind: 'furniture' as const,
        title: this.label(p),
        selected: p.id === sel,
      })),
    ];
  });

  constructor() {
    // A new unit (first load or navigation to a neighbour) restores its own arrangement, or the
    // one in the link fragment.
    effect(() => {
      const u = this.unit();
      untracked(() => this.load(u));
    });
  }

  label(p: PlacedPiece): string {
    const item = catalogueItem(p.item);
    return item ? pieceLabel(item) : p.item;
  }

  name(p: PlacedPiece): string {
    return catalogueItem(p.item)?.name ?? p.item;
  }

  size(p: PlacedPiece): string {
    const item = catalogueItem(p.item);
    return item ? pieceSize(item) : '';
  }

  icon(p: PlacedPiece): string {
    return catalogueItem(p.item)?.icon ?? 'lucideSquare';
  }

  /** The row in the panel and the polygon on the plan select the same piece. */
  select(id: string): void {
    this.selectedId.set(id);
  }

  // --- placing and editing

  add(f: CatalogueItem): void {
    const u = this.unit();
    const frame = this.frame();
    if (!frame || !u.plan?.ring || this.pieces().length >= MAX_PIECES) return;
    const [cx, cy] = outlineCentre(u.plan.ring, frame);
    // Each new piece lands 0.3 m further down and right (eight steps, then from the centre again),
    // so pieces added in a row do not hide each other.
    const n = this.pieces().length % 8;
    const id = `p${++this.seq}`;
    this.update((list) => [
      ...list,
      { id, item: f.id, cx_m: cx + n * 0.3, cy_m: cy + n * 0.3, rot: 0, flip: false },
    ]);
    this.selectedId.set(id);
  }

  rotate(): void {
    this.edit((p) => ({ ...p, rot: ((p.rot + 90) % 360) as Rotation }));
  }

  flip(): void {
    this.edit((p) => ({ ...p, flip: !p.flip }));
  }

  remove(): void {
    const id = this.selectedId();
    if (!id) return;
    this.update((list) => list.filter((p) => p.id !== id));
    this.selectedId.set(null);
  }

  clear(): void {
    this.update(() => []);
    this.selectedId.set(null);
  }

  onMoved(mv: PolygonMove): void {
    const f = this.frame();
    if (!f) return;
    this.update((list) =>
      list.map((p) =>
        p.id === mv.id
          ? {
              ...p,
              cx_m: Math.round((p.cx_m + (mv.dx * f.width) / f.k) * 100) / 100,
              cy_m: Math.round((p.cy_m + (mv.dy * f.height) / f.k) * 100) / 100,
            }
          : p,
      ),
    );
  }

  /** A tap on a piece selects it; a tap on the unit outline (the floor) deselects. */
  onSelected(id: string): void {
    this.selectedId.set(id === this.unit().unit_id ? null : id);
  }

  onKey(ev: KeyboardEvent): void {
    const tag = (ev.target as HTMLElement | null)?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    if (!this.selected()) return;
    if (ev.key === 'Delete' || ev.key === 'Backspace') this.remove();
    else if (ev.key === 'r' || ev.key === 'R') this.rotate();
    else if (ev.key === 'f' || ev.key === 'F') this.flip();
    else if (ev.key === 'Escape') this.selectedId.set(null);
    else return;
    ev.preventDefault();
  }

  setWall(ev: Event | null): void {
    const v = ev ? (ev.target as HTMLInputElement).value : null;
    this.wall.set(v && /^#[0-9a-f]{6}$/i.test(v) ? v.toLowerCase() : null);
    this.persist();
  }

  // --- sharing (ADR-0020 Decision 8)

  async share(): Promise<void> {
    const url = `${location.origin}${location.pathname}#l=${encodeLayout(this.layout())}`;
    const nav = navigator as Navigator & { share?: (d: ShareData) => Promise<void> };
    try {
      if (nav.share && /Mobi|Android/i.test(navigator.userAgent)) {
        await nav.share({ title: `${this.unit().code}: my arrangement`, url });
        this.say('lucideShare2', 'Shared');
        return;
      }
      await navigator.clipboard.writeText(url);
      this.shareUrl.set(null);
      this.say('lucideCopy', 'Link copied: whoever opens it sees this arrangement');
    } catch {
      this.shareUrl.set(url); // no clipboard (or the share sheet was closed): show the link to copy
    }
  }

  restoreOwn(): void {
    const own = this.own();
    if (!own) return;
    this.applyLayout(own);
    this.shared.set(false);
    this.own.set(null);
    this.say('lucideSave', `Back to your saved arrangement · ${own.pieces.length} pieces`);
  }

  selectAll(ev: FocusEvent): void {
    (ev.target as HTMLInputElement).select();
  }

  // --- persistence (ADR-0020 Decision 5)

  private layout(): Layout {
    const l: Layout = {
      v: 1,
      pieces: this.pieces().map(({ item, cx_m, cy_m, rot, flip }) => ({
        item,
        cx_m,
        cy_m,
        rot,
        flip,
      })),
    };
    if (this.wall()) l.wall_colour = this.wall()!;
    return l;
  }

  private key(): string {
    return layoutKey(location.host, this.slug(), this.unit().code);
  }

  private load(u: UnitDoc): void {
    if (this.loadedFor === u.code) return;
    this.loadedFor = u.code;
    this.selectedId.set(null);
    this.shareUrl.set(null);
    this.fade.set(false);
    const own = loadLayout(this.key());
    const linked = layoutFromFragment(this.route.snapshot.fragment);
    if (linked && (linked.pieces.length || linked.wall_colour)) {
      this.applyLayout(linked);
      this.shared.set(true);
      this.own.set(own);
      return;
    }
    this.shared.set(false);
    this.own.set(null);
    this.applyLayout(own ?? { v: 1, pieces: [] });
    if (own?.pieces.length) {
      this.say('lucideSave', `Saved in this browser · ${own.pieces.length} pieces`, 0);
    }
  }

  private applyLayout(l: Layout): void {
    this.pieces.set(l.pieces.map((p) => ({ ...p, id: `p${++this.seq}` })));
    this.wall.set(l.wall_colour ?? null);
  }

  private edit(fn: (p: Piece) => Piece): void {
    const id = this.selectedId();
    if (!id) return;
    this.update((list) => list.map((p) => (p.id === id ? fn(p) : p)));
  }

  private update(fn: (list: Piece[]) => Piece[]): void {
    this.pieces.update(fn);
    this.persist();
  }

  /** Every change is saved; the first change to a shared arrangement makes it the buyer's own. */
  private persist(): void {
    this.shared.set(false);
    this.own.set(null);
    this.shareUrl.set(null);
    const l = this.layout();
    const ok = saveLayout(this.key(), l);
    const n = l.pieces.length;
    if (!n && !l.wall_colour) this.say('lucideTrash2', 'Nothing placed; nothing kept', 4000);
    else if (ok)
      this.say('lucideSave', `Saved in this browser · ${n} ${n === 1 ? 'piece' : 'pieces'}`, 0);
    else
      this.say(
        'lucideTriangleAlert',
        'This browser blocks storage: the arrangement lasts for this page only',
        0,
      );
  }

  private say(icon: string, text: string, ms = 4000): void {
    this.status.set({ icon, text });
    if (this.statusTimer) clearTimeout(this.statusTimer);
    this.statusTimer = ms ? setTimeout(() => this.status.set(null), ms) : null;
  }
}
