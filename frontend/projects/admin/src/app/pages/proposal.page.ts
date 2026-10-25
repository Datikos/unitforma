import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { BoundaryOut, ProposalDecide, ProposalItemOut, ProposalOut, SheetOut, UnitOut, UnitformaApi, problemMessage } from 'api-client';
import { PlanPolygon, PlanViewerComponent, Ring } from 'plan-viewer';

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
  imports: [FormsModule, DecimalPipe, MatCardModule, MatButtonModule, MatFormFieldModule, MatInputModule, MatSelectModule, RouterLink, PlanViewerComponent],
  template: `
    <div class="uf-page">
      <div class="uf-page-header">
        <h2>Revision diff @if (proposal(); as p) { · {{ p.status }} }</h2>
        <a mat-stroked-button [routerLink]="['..']">All diffs</a>
      </div>
      @if (error()) { <p class="uf-error">{{ error() }}</p> }
      @if (proposal(); as p) {
        <div class="uf-toolbar">
          <mat-form-field appearance="outline" class="uf-pages">
            <mat-label>Page</mat-label>
            <mat-select [value]="pairIndex()" (valueChange)="pairIndex.set($event)">
              @for (pr of pairs(); track pr.newSheetId; let i = $index) { <mat-option [value]="i">Page {{ pageNo(pr.newSheetId) }} · {{ itemsOnPair(pr).length }} item(s)</mat-option> }
            </mat-select>
          </mat-form-field>
          <span class="uf-muted">{{ summaryText() }}</span>
          <span class="uf-spacer"></span>
          <button mat-flat-button [disabled]="busy() || p.status !== 'open' || pendingOf('matched') === 0" (click)="acceptAll(['matched'])">
            Accept {{ pendingOf('matched') }} matched
          </button>
        </div>
        @if (pair(); as pr) {
          <div class="uf-split">
            <div>
              <h4>Previous revision @if (oldSheet(); as s) { · page {{ s.page_no }} }</h4>
              <uf-plan-viewer [src]="oldSheet()?.raster_url ?? null" [width]="oldSheet()?.raster_width ?? 1000" [height]="oldSheet()?.raster_height ?? 700" [polygons]="oldPolygons()" mode="view" (polygonSelected)="selectByUnit($event)" />
            </div>
            <div>
              <h4>New revision @if (newSheet(); as s) { · page {{ s.page_no }} · {{ s.assignment_status }} }</h4>
              <uf-plan-viewer [src]="newSheet()?.raster_url ?? null" [width]="newSheet()?.raster_width ?? 1000" [height]="newSheet()?.raster_height ?? 700" [polygons]="newPolygons()" mode="view" (polygonSelected)="selectByPolygon($event)" />
            </div>
          </div>
        }
        <mat-card appearance="outlined">
          <mat-card-header><mat-card-title>Proposed changes</mat-card-title></mat-card-header>
          <mat-card-content>
            <table class="uf-items">
              <thead><tr><th>Change</th><th>Current units</th><th>New drawing</th><th>Confidence</th><th>Decision</th><th></th></tr></thead>
              <tbody>
                @for (it of visibleItems(); track it.id) {
                  <tr [class.uf-selected]="it.id === selectedItemId()" (click)="selectedItemId.set(it.id)">
                    <td><strong>{{ it.kind }}</strong></td>
                    <td>@for (id of it.old_unit_ids; track id) { <span class="uf-chip">{{ code(id) }}</span> }</td>
                    <td>@for (l of it.labels; track $index) { <span class="uf-chip uf-chip--new">{{ l ?? 'unlabelled' }}</span> } @if (!it.labels.length) { <span class="uf-muted">—</span> }</td>
                    <td>{{ +it.confidence * 100 | number: '1.0-0' }} %</td>
                    <td>
                      {{ it.decision }}
                      @if (it.decision === 'accepted' && it.result['code']) { → {{ it.result['code'] }} }
                    </td>
                    <td class="uf-actions">
                      @if (it.decision === 'pending' && p.status === 'open') {
                        @switch (it.kind) {
                          @case ('new') {
                            <mat-form-field appearance="outline" class="uf-small"><mat-label>Code</mat-label><input matInput [(ngModel)]="codeFor[it.id]" [name]="'c' + it.id" placeholder="auto" (click)="$event.stopPropagation()" /></mat-form-field>
                            <mat-form-field appearance="outline" class="uf-small"><mat-label>Type</mat-label>
                              <mat-select [(ngModel)]="typeFor[it.id]" [name]="'t' + it.id" (click)="$event.stopPropagation()"><mat-option value="apartment">Apartment</mat-option><mat-option value="commercial">Commercial</mat-option><mat-option value="parking">Parking</mat-option><mat-option value="storage">Storage</mat-option></mat-select>
                            </mat-form-field>
                          }
                          @case ('relabelled') {
                            <mat-form-field appearance="outline" class="uf-small"><mat-label>New code (optional)</mat-label><input matInput [(ngModel)]="codeFor[it.id]" [name]="'c' + it.id" (click)="$event.stopPropagation()" /></mat-form-field>
                          }
                          @case ('merged') {
                            <mat-form-field appearance="outline" class="uf-small"><mat-label>Keeps its id</mat-label>
                              <mat-select [(ngModel)]="survivorFor[it.id]" [name]="'s' + it.id" (click)="$event.stopPropagation()">
                                @for (id of it.old_unit_ids; track id) { <mat-option [value]="id">{{ code(id) }}</mat-option> }
                              </mat-select>
                            </mat-form-field>
                          }
                          @case ('split') {
                            <mat-form-field appearance="outline" class="uf-small"><mat-label>Part that keeps {{ code(it.old_unit_ids[0]) }}</mat-label>
                              <mat-select [(ngModel)]="inheritFor[it.id]" [name]="'i' + it.id" (click)="$event.stopPropagation()">
                                @for (l of it.labels; track $index) { <mat-option [value]="$index">{{ l ?? 'part ' + ($index + 1) }}</mat-option> }
                              </mat-select>
                            </mat-form-field>
                            @for (l of it.labels; track $index) {
                              @if ($index !== (inheritFor[it.id] ?? defaultInherit(it))) {
                                <mat-form-field appearance="outline" class="uf-small"><mat-label>Code for {{ l ?? 'part ' + ($index + 1) }}</mat-label><input matInput [(ngModel)]="splitCodes[it.id + ':' + $index]" [name]="'sc' + it.id + $index" placeholder="auto" (click)="$event.stopPropagation()" /></mat-form-field>
                              }
                            }
                          }
                        }
                        @if (it.kind !== 'complex') {
                          <button mat-flat-button [disabled]="busy()" (click)="decide(it, 'accept'); $event.stopPropagation()">Accept</button>
                        }
                        <button mat-stroked-button [disabled]="busy()" (click)="decide(it, 'reject'); $event.stopPropagation()">Reject</button>
                      }
                    </td>
                  </tr>
                } @empty { <tr><td colspan="6" class="uf-muted">No proposed changes on this page.</td></tr> }
              </tbody>
            </table>
          </mat-card-content>
        </mat-card>
      }
    </div>
  `,
  styles: `
    .uf-toolbar { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
    .uf-pages { min-width: 220px; }
    .uf-spacer { flex: 1; }
    .uf-split { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    .uf-split h4 { margin: 0 0 0.25rem; }
    .uf-split uf-plan-viewer { height: 50vh; }
    .uf-items { width: 100%; border-collapse: collapse; }
    .uf-items th, .uf-items td { text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
    .uf-items tr { cursor: pointer; }
    .uf-selected { background: rgba(245, 158, 11, 0.12); }
    .uf-chip { display: inline-block; padding: 0 0.4rem; margin: 0 0.2rem 0.2rem 0; border-radius: 4px; background: #dbeafe; font-size: 0.8rem; }
    .uf-chip--new { background: #ede9fe; }
    .uf-actions { display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center; }
    .uf-small { width: 150px; }
    @media (max-width: 900px) { .uf-split { grid-template-columns: 1fr; } }
  `,
})
export class ProposalPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly proposalId = input.required<string>();
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
      if (it.new_sheet_id && it.old_sheet_id && !seen.has(it.new_sheet_id)) seen.set(it.new_sheet_id, { oldSheetId: it.old_sheet_id, newSheetId: it.new_sheet_id });
    }
    return [...seen.values()].sort((a, b) => this.pageNo(a.newSheetId) - this.pageNo(b.newSheetId));
  });
  readonly pair = computed(() => this.pairs()[this.pairIndex()] ?? null);
  readonly oldSheet = computed(() => (this.pair() ? this.sheets().get(this.pair()!.oldSheetId) ?? null : null));
  readonly newSheet = computed(() => (this.pair() ? this.sheets().get(this.pair()!.newSheetId) ?? null : null));
  readonly visibleItems = computed(() => (this.pair() ? this.itemsOnPair(this.pair()!) : []));
  readonly selectedItem = computed(() => this.visibleItems().find((i) => i.id === this.selectedItemId()) ?? null);
  readonly oldPolygons = computed<PlanPolygon[]>(() => {
    const pr = this.pair();
    if (!pr) return [];
    const sel = new Set(this.selectedItem()?.old_unit_ids ?? []);
    return (this.oldBoundaries().get(pr.oldSheetId) ?? []).map((b) => ({ id: b.unit_id, ring: b.polygon['ring'] as Ring, label: this.code(b.unit_id), status: b.status, selected: sel.has(b.unit_id) }));
  });
  readonly newPolygons = computed<PlanPolygon[]>(() => {
    const pr = this.pair();
    if (!pr) return [];
    const ghosts: PlanPolygon[] = (this.oldBoundaries().get(pr.oldSheetId) ?? []).map((b) => ({ id: 'ghost:' + b.id, ring: b.polygon['ring'] as Ring, kind: 'ghost' as const }));
    const cands: PlanPolygon[] = [];
    for (const it of this.visibleItems()) {
      it.new_rings.forEach((ring, i) => cands.push({ id: `${it.id}:${i}`, ring: ring as Ring, label: `${it.kind}${it.labels[i] ? ' · ' + it.labels[i] : ''}`, kind: 'candidate', selected: it.id === this.selectedItemId() }));
    }
    return [...ghosts, ...cands];
  });

  constructor() {
    toObservable(this.proposalId).subscribe(() => void this.load());
  }

  async load(): Promise<void> {
    try {
      const [p, units] = await Promise.all([this.api.getProposal(this.tenantId(), this.proposalId()), this.api.listUnits(this.tenantId(), this.projectId(), true)]);
      p.items ??= [];
      this.proposal.set(p);
      this.units.set(new Map(units.map((u) => [u.id, u])));
      const sheetIds = new Set<string>();
      for (const it of p.items) {
        if (it.old_sheet_id) sheetIds.add(it.old_sheet_id);
        if (it.new_sheet_id) sheetIds.add(it.new_sheet_id);
      }
      const loaded = await Promise.all([...sheetIds].map((id) => this.api.getSheet(this.tenantId(), id).catch(() => null)));
      this.sheets.set(new Map(loaded.filter((s): s is SheetOut => !!s).map((s) => [s.id, s])));
      const oldIds = [...new Set(p.items.map((i) => i.old_sheet_id).filter((x): x is string => !!x))];
      const bounds = await Promise.all(oldIds.map((id) => this.api.listBoundaries(this.tenantId(), id).catch(() => [] as BoundaryOut[])));
      this.oldBoundaries.set(new Map(oldIds.map((id, i) => [id, bounds[i]])));
      for (const it of p.items) {
        if (it.kind === 'merged' && !this.survivorFor[it.id]) this.survivorFor[it.id] = this.defaultSurvivor(it);
        if (it.kind === 'new' && !this.typeFor[it.id]) this.typeFor[it.id] = 'apartment';
      }
    } catch (e) {
      this.error.set(problemMessage(e));
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
    return (this.proposal()?.items ?? []).filter((i) => i.kind === kind && i.decision === 'pending').length;
  }

  summaryText(): string {
    const s = (this.proposal()?.summary ?? {}) as Record<string, number>;
    return ['matched', 'relabelled', 'split', 'merged', 'new', 'missing', 'complex'].filter((k) => s[k]).map((k) => `${s[k]} ${k}`).join(' · ');
  }

  defaultInherit(it: ProposalItemOut): number {
    let best = 0;
    let ratio = -1;
    for (const [, idx, r] of it.overlaps as [string, number, number][]) if (r > ratio) [best, ratio] = [idx, r];
    return best;
  }

  defaultSurvivor(it: ProposalItemOut): string {
    let best = it.old_unit_ids[0];
    let ratio = -1;
    for (const [uid, , r] of it.overlaps as [string, number, number][]) if (r > ratio) [best, ratio] = [uid, r];
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
        body.codes = it.labels.map((_, i) => (i === keep ? null : this.splitCodes[it.id + ':' + i] || null));
      }
    }
    await this.run(() => this.api.decideProposalItem(this.tenantId(), this.proposalId(), it.id, body));
  }

  acceptAll(kinds: string[]): Promise<void> {
    return this.run(() => this.api.acceptProposalItems(this.tenantId(), this.proposalId(), kinds));
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
