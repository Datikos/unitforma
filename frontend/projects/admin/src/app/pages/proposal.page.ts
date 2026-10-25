import { DecimalPipe } from '@angular/common';
import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  BoundaryOut,
  ProposalDecide,
  ProposalItemOut,
  ProposalOut,
  SheetOut,
  UnitOut,
  UnitformaApi,
  problemMessage,
} from 'api-client';
import { PlanPolygon, PlanViewerComponent, Ring } from 'plan-viewer';
import {
  EmptyStateComponent,
  HeaderFact,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
  labelOf,
} from 'ui';
import { RouteInfo } from '../core/route-info';
import { ToastService } from '../ui/toast.service';

interface PagePair {
  oldSheetId: string;
  newSheetId: string;
}

/**
 * Revision diff review (plan §13.3): old revision on the left with its boundaries, new revision on the
 * right with the proposed polygons and the old boundaries as ghosts; each item is accepted (applied
 * through identity-preserving operations) or rejected.
 */
@Component({
  selector: 'uf-proposal-page',
  imports: [
    FormsModule,
    DecimalPipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    RouterLink,
    NgIcon,
    PlanViewerComponent,
    PageHeaderComponent,
    SectionCardComponent,
    StatusChipComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header title="Revision diff" icon="lucideGitCompare" [facts]="facts()">
        <ng-container actions>
          <a mat-stroked-button [routerLink]="['..']"
            ><ng-icon name="lucideArrowLeft" /> All diffs</a
          >
          @if (proposal(); as p) {
            <button
              mat-flat-button
              [disabled]="busy() || p.status !== 'open' || pendingOf('matched') === 0"
              (click)="acceptAll(['matched'])"
            >
              <ng-icon name="lucideCheck" /> Accept {{ pendingOf('matched') }} matched
            </button>
          }
        </ng-container>
      </uf-page-header>
      @if (error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }
      @if (proposal(); as p) {
        <p class="uf-hint">
          Accepting a relabel keeps the unit id and changes its code; a split or merge records
          lineage so prices and leads stay attached to the right units. Rejected items leave the
          current units as they are.
        </p>
        <div class="uf-toolbar">
          <mat-form-field appearance="outline" class="uf-pages" subscriptSizing="dynamic">
            <mat-label>Page</mat-label>
            <mat-select [value]="pairIndex()" (valueChange)="pairIndex.set($event)">
              @for (pr of pairs(); track pr.newSheetId; let i = $index) {
                <mat-option [value]="i"
                  >Page {{ pageNo(pr.newSheetId) }} ·
                  {{ itemsOnPair(pr).length }} item(s)</mat-option
                >
              }
            </mat-select>
          </mat-form-field>
          <div class="uf-chips">
            @for (k of kindCounts(); track k.kind) {
              <uf-status-chip
                domain="proposal.kind"
                [value]="k.kind"
                [label]="k.count + ' ' + k.kind"
              />
            }
          </div>
        </div>
        @if (pair(); as pr) {
          <div class="uf-split">
            <div>
              <h4>
                <ng-icon name="lucideHistory" /> Previous revision
                @if (oldSheet(); as s) {
                  · page {{ s.page_no }}
                }
              </h4>
              <uf-plan-viewer
                [src]="oldSheet()?.raster_url ?? null"
                [width]="oldSheet()?.raster_width ?? 1000"
                [height]="oldSheet()?.raster_height ?? 700"
                [polygons]="oldPolygons()"
                mode="view"
                (polygonSelected)="selectByUnit($event)"
              />
            </div>
            <div>
              <h4>
                <ng-icon name="lucideSparkles" /> New revision
                @if (newSheet(); as s) {
                  · page {{ s.page_no }}
                  <uf-status-chip domain="sheet.assignment" [value]="s.assignment_status" />
                }
              </h4>
              <uf-plan-viewer
                [src]="newSheet()?.raster_url ?? null"
                [width]="newSheet()?.raster_width ?? 1000"
                [height]="newSheet()?.raster_height ?? 700"
                [polygons]="newPolygons()"
                mode="view"
                (polygonSelected)="selectByPolygon($event)"
              />
            </div>
          </div>
        }
        <uf-section-card
          title="Proposed changes on this page"
          icon="lucideGitCompare"
          [count]="visibleItems().length"
          [summary]="pendingOnPage() + ' pending'"
          [flush]="true"
          [collapsible]="false"
        >
          <table class="uf-plain uf-items">
            <thead>
              <tr>
                <th>Change</th>
                <th>Current units</th>
                <th>New drawing</th>
                <th>Confidence</th>
                <th>Decision</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (it of visibleItems(); track it.id) {
                <tr
                  [class.uf-selected]="it.id === selectedItemId()"
                  (click)="selectedItemId.set(it.id)"
                >
                  <td><uf-status-chip domain="proposal.kind" [value]="it.kind" /></td>
                  <td>
                    @for (id of it.old_unit_ids; track id) {
                      <span class="uf-chip">{{ code(id) }}</span>
                    } @empty {
                      <span class="uf-muted">—</span>
                    }
                  </td>
                  <td>
                    @for (l of it.labels; track $index) {
                      <span class="uf-chip uf-tone-info">{{ l ?? 'unlabelled' }}</span>
                    }
                    @if (!it.labels.length) {
                      <span class="uf-muted">—</span>
                    }
                  </td>
                  <td>
                    <span
                      class="uf-chip"
                      [class.uf-tone-good]="+it.confidence >= 0.85"
                      [class.uf-tone-warning]="+it.confidence < 0.85"
                      title="How sure the engine is; 85 % and above counts as confident"
                      >{{ +it.confidence * 100 | number: '1.0-0' }} %</span
                    >
                  </td>
                  <td>
                    <uf-status-chip domain="proposal.decision" [value]="it.decision" />
                    @if (it.decision === 'accepted' && it.result['code']) {
                      <span class="uf-small">→ {{ it.result['code'] }}</span>
                    }
                  </td>
                  <td class="uf-actions">
                    @if (it.decision === 'pending' && p.status === 'open') {
                      @switch (it.kind) {
                        @case ('new') {
                          <mat-form-field appearance="outline" class="uf-small"
                            ><mat-label>Code</mat-label
                            ><input
                              matInput
                              [(ngModel)]="codeFor[it.id]"
                              [name]="'c' + it.id"
                              placeholder="auto"
                              (click)="$event.stopPropagation()"
                          /></mat-form-field>
                          <mat-form-field appearance="outline" class="uf-small"
                            ><mat-label>Type</mat-label>
                            <mat-select
                              [(ngModel)]="typeFor[it.id]"
                              [name]="'t' + it.id"
                              (click)="$event.stopPropagation()"
                              ><mat-option value="apartment">Apartment</mat-option
                              ><mat-option value="commercial">Commercial</mat-option
                              ><mat-option value="parking">Parking</mat-option
                              ><mat-option value="storage">Storage</mat-option></mat-select
                            >
                          </mat-form-field>
                        }
                        @case ('relabelled') {
                          <mat-form-field appearance="outline" class="uf-small"
                            ><mat-label>New code (optional)</mat-label
                            ><input
                              matInput
                              [(ngModel)]="codeFor[it.id]"
                              [name]="'c' + it.id"
                              (click)="$event.stopPropagation()"
                          /></mat-form-field>
                        }
                        @case ('merged') {
                          <mat-form-field appearance="outline" class="uf-small"
                            ><mat-label>Keeps its id</mat-label>
                            <mat-select
                              [(ngModel)]="survivorFor[it.id]"
                              [name]="'s' + it.id"
                              (click)="$event.stopPropagation()"
                            >
                              @for (id of it.old_unit_ids; track id) {
                                <mat-option [value]="id">{{ code(id) }}</mat-option>
                              }
                            </mat-select>
                          </mat-form-field>
                        }
                        @case ('split') {
                          <mat-form-field appearance="outline" class="uf-small"
                            ><mat-label>Part that keeps {{ code(it.old_unit_ids[0]) }}</mat-label>
                            <mat-select
                              [(ngModel)]="inheritFor[it.id]"
                              [name]="'i' + it.id"
                              (click)="$event.stopPropagation()"
                            >
                              @for (l of it.labels; track $index) {
                                <mat-option [value]="$index">{{
                                  l ?? 'part ' + ($index + 1)
                                }}</mat-option>
                              }
                            </mat-select>
                          </mat-form-field>
                          @for (l of it.labels; track $index) {
                            @if ($index !== (inheritFor[it.id] ?? defaultInherit(it))) {
                              <mat-form-field appearance="outline" class="uf-small"
                                ><mat-label>Code for {{ l ?? 'part ' + ($index + 1) }}</mat-label
                                ><input
                                  matInput
                                  [(ngModel)]="splitCodes[it.id + ':' + $index]"
                                  [name]="'sc' + it.id + $index"
                                  placeholder="auto"
                                  (click)="$event.stopPropagation()"
                              /></mat-form-field>
                            }
                          }
                        }
                      }
                      @if (it.kind !== 'complex') {
                        <button
                          mat-flat-button
                          [disabled]="busy()"
                          (click)="decide(it, 'accept'); $event.stopPropagation()"
                        >
                          <ng-icon name="lucideCheck" /> Accept
                        </button>
                      } @else {
                        <span class="uf-hint"
                          >Complex: resolve in the sheet editor, then reject here.</span
                        >
                      }
                      <button
                        mat-stroked-button
                        [disabled]="busy()"
                        (click)="decide(it, 'reject'); $event.stopPropagation()"
                      >
                        <ng-icon name="lucideX" /> Reject
                      </button>
                    }
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="6">
                    <uf-empty-state
                      icon="lucideCheck"
                      title="No proposed changes on this page"
                      [compact]="true"
                    />
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </uf-section-card>
      } @else if (loaded()) {
        <uf-empty-state
          icon="lucideGitCompare"
          title="This revision diff is not available"
          text="It may belong to another project or have been removed."
        />
      }
    </div>
  `,
  styles: `
    .uf-pages {
      min-width: 220px;
    }
    .uf-split {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }
    .uf-split > div {
      background: var(--uf-surface);
      border: 1px solid var(--uf-border);
      border-radius: var(--uf-radius);
      padding: 0.5rem;
    }
    .uf-split h4 {
      margin: 0 0 0.35rem;
      display: flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.95rem;
    }
    .uf-split h4 ng-icon {
      color: var(--uf-primary);
    }
    .uf-split uf-plan-viewer {
      height: 50vh;
      display: block;
    }
    .uf-items tr {
      cursor: pointer;
    }
    .uf-selected td {
      background: var(--uf-tone-warning-bg);
    }
    .uf-actions {
      display: flex;
      gap: 0.4rem;
      flex-wrap: wrap;
      align-items: center;
    }
    .uf-small {
      width: 150px;
    }
    a ng-icon,
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.2rem;
    }
    @media (max-width: 900px) {
      .uf-split {
        grid-template-columns: 1fr;
      }
    }
  `,
})
export class ProposalPage {
  private readonly api = inject(UnitformaApi);
  private readonly toast = inject(ToastService);
  private readonly routeInfo = inject(RouteInfo);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly proposalId = input.required<string>();
  readonly loaded = signal(false);
  readonly proposal = signal<ProposalOut | null>(null);
  readonly units = signal<Map<string, UnitOut>>(new Map());
  readonly sheets = signal<Map<string, SheetOut>>(new Map());
  readonly oldBoundaries = signal<Map<string, BoundaryOut[]>>(new Map());
  readonly pairIndex = signal(0);
  readonly selectedItemId = signal<string | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  codeFor: Record<string, string> = {};
  typeFor: Record<string, 'apartment' | 'commercial' | 'parking' | 'storage'> = {};
  survivorFor: Record<string, string> = {};
  inheritFor: Record<string, number> = {};
  splitCodes: Record<string, string> = {};

  readonly pairs = computed<PagePair[]>(() => {
    const seen = new Map<string, PagePair>();
    for (const it of this.proposal()?.items ?? []) {
      if (it.new_sheet_id && it.old_sheet_id && !seen.has(it.new_sheet_id))
        seen.set(it.new_sheet_id, { oldSheetId: it.old_sheet_id, newSheetId: it.new_sheet_id });
    }
    return [...seen.values()].sort((a, b) => this.pageNo(a.newSheetId) - this.pageNo(b.newSheetId));
  });
  readonly pair = computed(() => this.pairs()[this.pairIndex()] ?? null);
  readonly oldSheet = computed(() =>
    this.pair() ? (this.sheets().get(this.pair()!.oldSheetId) ?? null) : null,
  );
  readonly newSheet = computed(() =>
    this.pair() ? (this.sheets().get(this.pair()!.newSheetId) ?? null) : null,
  );
  readonly visibleItems = computed(() => (this.pair() ? this.itemsOnPair(this.pair()!) : []));
  readonly selectedItem = computed(
    () => this.visibleItems().find((i) => i.id === this.selectedItemId()) ?? null,
  );
  readonly oldPolygons = computed<PlanPolygon[]>(() => {
    const pr = this.pair();
    if (!pr) return [];
    const sel = new Set(this.selectedItem()?.old_unit_ids ?? []);
    return (this.oldBoundaries().get(pr.oldSheetId) ?? []).map((b) => ({
      id: b.unit_id,
      ring: b.polygon['ring'] as Ring,
      label: this.code(b.unit_id),
      status: b.status,
      selected: sel.has(b.unit_id),
    }));
  });
  readonly newPolygons = computed<PlanPolygon[]>(() => {
    const pr = this.pair();
    if (!pr) return [];
    const ghosts: PlanPolygon[] = (this.oldBoundaries().get(pr.oldSheetId) ?? []).map((b) => ({
      id: 'ghost:' + b.id,
      ring: b.polygon['ring'] as Ring,
      kind: 'ghost' as const,
    }));
    const cands: PlanPolygon[] = [];
    for (const it of this.visibleItems()) {
      it.new_rings.forEach((ring, i) =>
        cands.push({
          id: `${it.id}:${i}`,
          ring: ring as Ring,
          label: `${it.kind}${it.labels[i] ? ' · ' + it.labels[i] : ''}`,
          kind: 'candidate',
          selected: it.id === this.selectedItemId(),
        }),
      );
    }
    return [...ghosts, ...cands];
  });

  readonly kindCounts = computed(() => {
    const s = (this.proposal()?.summary ?? {}) as Record<string, number>;
    return ['matched', 'relabelled', 'split', 'merged', 'new', 'missing', 'complex']
      .filter((k) => s[k])
      .map((k) => ({ kind: k, count: s[k] }));
  });
  readonly pendingOnPage = computed(
    () => this.visibleItems().filter((i) => i.decision === 'pending').length,
  );
  readonly facts = computed<HeaderFact[]>(() => {
    const p = this.proposal();
    if (!p) return [];
    const items = p.items ?? [];
    return [
      { domain: 'proposal.status', status: p.status },
      { label: 'Items', value: items.length },
      {
        domain: 'proposal.decision',
        status: 'pending',
        value: `${items.filter((i) => i.decision === 'pending').length} pending`,
      },
      {
        domain: 'proposal.decision',
        status: 'accepted',
        value: `${items.filter((i) => i.decision === 'accepted').length} accepted`,
      },
    ];
  });

  constructor() {
    toObservable(this.proposalId).subscribe(() => void this.load());
    effect(() => {
      const p = this.proposal();
      this.routeInfo.setLeaf(
        p ? `${labelOf('proposal.status', p.status)} · ${(p.items ?? []).length} items` : null,
      );
    });
  }

  async load(): Promise<void> {
    try {
      const [p, units] = await Promise.all([
        this.api.getProposal(this.tenantId(), this.proposalId()),
        this.api.listUnits(this.tenantId(), this.projectId(), true),
      ]);
      p.items ??= [];
      this.proposal.set(p);
      this.units.set(new Map(units.map((u) => [u.id, u])));
      const sheetIds = new Set<string>();
      for (const it of p.items) {
        if (it.old_sheet_id) sheetIds.add(it.old_sheet_id);
        if (it.new_sheet_id) sheetIds.add(it.new_sheet_id);
      }
      const loaded = await Promise.all(
        [...sheetIds].map((id) => this.api.getSheet(this.tenantId(), id).catch(() => null)),
      );
      this.sheets.set(new Map(loaded.filter((s): s is SheetOut => !!s).map((s) => [s.id, s])));
      const oldIds = [
        ...new Set(p.items.map((i) => i.old_sheet_id).filter((x): x is string => !!x)),
      ];
      const bounds = await Promise.all(
        oldIds.map((id) =>
          this.api.listBoundaries(this.tenantId(), id).catch(() => [] as BoundaryOut[]),
        ),
      );
      this.oldBoundaries.set(new Map(oldIds.map((id, i) => [id, bounds[i]])));
      for (const it of p.items) {
        if (it.kind === 'merged' && !this.survivorFor[it.id])
          this.survivorFor[it.id] = this.defaultSurvivor(it);
        if (it.kind === 'new' && !this.typeFor[it.id]) this.typeFor[it.id] = 'apartment';
      }
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.loaded.set(true);
    }
  }

  pageNo(sheetId: string): number {
    return this.sheets().get(sheetId)?.page_no ?? 0;
  }

  itemsOnPair(pr: PagePair): ProposalItemOut[] {
    return (this.proposal()?.items ?? []).filter((i) => i.new_sheet_id === pr.newSheetId);
  }

  code(unitId: string): string {
    return this.units().get(unitId)?.code ?? unitId.slice(0, 8);
  }

  pendingOf(kind: string): number {
    return (this.proposal()?.items ?? []).filter((i) => i.kind === kind && i.decision === 'pending')
      .length;
  }

  defaultInherit(it: ProposalItemOut): number {
    let best = 0;
    let ratio = -1;
    for (const [, idx, r] of it.overlaps as [string, number, number][])
      if (r > ratio) [best, ratio] = [idx, r];
    return best;
  }

  defaultSurvivor(it: ProposalItemOut): string {
    let best = it.old_unit_ids[0];
    let ratio = -1;
    for (const [uid, , r] of it.overlaps as [string, number, number][])
      if (r > ratio) [best, ratio] = [uid, r];
    return best;
  }

  selectByUnit(unitId: string): void {
    const it = this.visibleItems().find((i) => i.old_unit_ids.includes(unitId));
    if (it) this.selectedItemId.set(it.id);
  }

  selectByPolygon(id: string): void {
    if (id.startsWith('ghost:')) return;
    this.selectedItemId.set(id.split(':')[0]);
  }

  async decide(it: ProposalItemOut, decision: 'accept' | 'reject'): Promise<void> {
    const body: ProposalDecide = { decision };
    if (decision === 'accept') {
      if (it.kind === 'new' || it.kind === 'relabelled') body.code = this.codeFor[it.id] || null;
      if (it.kind === 'new') body.unit_type = this.typeFor[it.id] ?? 'apartment';
      if (it.kind === 'merged') body.survivor_id = this.survivorFor[it.id] ?? null;
      if (it.kind === 'split') {
        const keep = this.inheritFor[it.id] ?? this.defaultInherit(it);
        body.inherit_index = keep;
        body.codes = it.labels.map((_, i) =>
          i === keep ? null : this.splitCodes[it.id + ':' + i] || null,
        );
      }
    }
    await this.run(async () => {
      await this.api.decideProposalItem(this.tenantId(), this.proposalId(), it.id, body);
      this.toast.ok(
        `${labelOf('proposal.kind', it.kind)} ${decision === 'accept' ? 'accepted' : 'rejected'}`,
      );
    });
  }

  acceptAll(kinds: string[]): Promise<void> {
    const n = kinds.reduce((a, k) => a + this.pendingOf(k), 0);
    return this.run(async () => {
      await this.api.acceptProposalItems(this.tenantId(), this.proposalId(), kinds);
      this.toast.ok(`${n} item${n === 1 ? '' : 's'} accepted`);
    });
  }

  private async run(fn: () => Promise<unknown>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await fn();
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}
