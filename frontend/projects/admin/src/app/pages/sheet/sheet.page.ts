import { DecimalPipe } from '@angular/common';
import { Component, computed, effect, inject, input } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { PlanViewerComponent } from 'plan-viewer';
import { HeaderFact, PageHeaderComponent, UF_ICONS } from 'ui';
import { RouteInfo } from '../../core/route-info';
import { SheetFloorsCardComponent } from './sheet-floors-card.component';
import { SheetUnitsTableComponent } from './sheet-units-table.component';
import { UNIT_TYPES, methodLabel } from './sheet.model';
import { SheetStore } from './sheet.store';

/** Sheet mapping editor: floor assignment, calibration, unit boundaries, vector suggestions, review (plan §13.1 steps 3–5). */
@Component({
  selector: 'uf-sheet-page',
  imports: [
    FormsModule,
    DecimalPipe,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatButtonToggleModule,
    RouterLink,
    NgIcon,
    PlanViewerComponent,
    PageHeaderComponent,
    SheetFloorsCardComponent,
    SheetUnitsTableComponent,
  ],
  providers: [SheetStore],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      @let s = store.sheet();
      <uf-page-header
        [title]="s ? 'Sheet · page ' + s.page_no : 'Sheet'"
        icon="lucideRuler"
        [facts]="facts()"
      >
        <ng-container actions>
          <a mat-stroked-button [routerLink]="['../../documents']"
            ><ng-icon name="lucideArrowLeft" /> Documents</a
          >
          @if (s && !s.excluded) {
            <button
              mat-button
              [disabled]="store.busy() || !store.units().length"
              (click)="store.readPrinted()"
              title="Takes the area printed inside each outline as the unit's printed area"
            >
              <ng-icon name="lucideScan" /> Read printed areas
            </button>
            <button
              mat-button
              [disabled]="store.busy() || store.units().length > 0"
              (click)="store.setExcluded(true)"
            >
              <ng-icon name="lucideBan" /> Exclude sheet
            </button>
            <button
              mat-flat-button
              [disabled]="store.busy() || store.draftCount() === 0"
              (click)="store.approve()"
            >
              <ng-icon name="lucideClipboardCheck" /> Approve {{ store.draftCount() }} draft unit{{
                store.draftCount() === 1 ? '' : 's'
              }}
            </button>
          }
        </ng-container>
      </uf-page-header>
      @if (store.error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }
      @if (store.notice(); as n) {
        <div class="uf-alert uf-alert--good" role="status">
          <ng-icon name="lucideCircleCheck" />{{ n }}
        </div>
      }

      @if (s) {
        @if (s.excluded) {
          <div class="uf-alert">
            <ng-icon name="lucideBan" />
            <div><strong>Excluded from mapping.</strong> {{ s.exclusion_reason }}</div>
            <span class="uf-spacer"></span>
            <button mat-stroked-button [disabled]="store.busy()" (click)="store.setExcluded(false)">
              Include again
            </button>
          </div>
        } @else {
          @if (store.duplicateOf(); as dup) {
            <div class="uf-alert uf-alert--warning">
              <ng-icon name="lucideInfo" />
              <div>
                This page repeats the units of page {{ dup }} (a reprint, e.g. a fire-safety or
                accessibility set). Map page {{ dup }} instead, or exclude this one.
              </div>
              <button
                mat-button
                [disabled]="store.busy()"
                (click)="store.setExcluded(true, 'reprint of page ' + dup)"
              >
                Exclude this page
              </button>
            </div>
          }
          <uf-sheet-floors-card />

          <div class="uf-toolbar tools">
            <mat-button-toggle-group
              [value]="store.mode()"
              (valueChange)="store.setMode($event)"
              hideSingleSelectionIndicator
              aria-label="Editor mode"
            >
              <mat-button-toggle value="view" title="Pan and zoom; click a unit to select it"
                ><ng-icon name="lucideMousePointer" /> View</mat-button-toggle
              >
              <mat-button-toggle value="calibrate" title="Click two points of a known distance"
                ><ng-icon name="lucideRuler" /> Calibrate</mat-button-toggle
              >
              <mat-button-toggle
                value="draw"
                [disabled]="!store.confirmedFloors().length"
                title="Click the corners of a unit, double-click to close"
                ><ng-icon name="lucidePenTool" /> Draw unit</mat-button-toggle
              >
            </mat-button-toggle-group>
            <button
              mat-stroked-button
              [disabled]="store.busy() || !store.confirmedFloors().length"
              (click)="store.suggest()"
            >
              <ng-icon name="lucideSparkles" /> Suggest boundaries
            </button>
            @if (!store.confirmedFloors().length) {
              <span class="uf-hint">Confirm a floor above before drawing or suggesting.</span>
            }
            <span class="uf-spacer"></span>
            <span class="uf-muted uf-small">{{ store.hintsText() }}</span>
          </div>
          <p class="uf-hint mode-hint">
            @switch (store.mode()) {
              @case ('view') {
                View: pan with the mouse, zoom with the wheel, click an outline to select it in the
                table below.
              }
              @case ('calibrate') {
                Calibrate: click two points whose real distance you know (a dimension line, a door
                width), then type the metres.
              }
              @case ('draw') {
                Draw: click each corner of the unit; double-click or press Enter to close. The
                outline becomes a draft unit at once.
              }
            }
          </p>

          @if (store.mode() === 'calibrate') {
            <div class="uf-card uf-form-row">
              <ng-icon name="lucideRuler" class="lead" />
              <span>{{
                store.calibPts()
                  ? 'Two points picked. Enter the real distance between them:'
                  : 'Click the first point on the drawing…'
              }}</span>
              <mat-form-field appearance="outline" subscriptSizing="dynamic"
                ><mat-label>Distance (m)</mat-label
                ><input
                  matInput
                  type="number"
                  step="0.01"
                  [(ngModel)]="store.distance"
                  name="distance"
              /></mat-form-field>
              <button
                mat-flat-button
                [disabled]="!store.calibPts() || !store.distance"
                (click)="store.calibrate()"
              >
                Apply scale
              </button>
            </div>
          }
          @if (store.mode() === 'draw' && !store.regionTarget()) {
            <div class="uf-card uf-form-row">
              <ng-icon name="lucidePenTool" class="lead" />
              <span>The next closed outline becomes:</span>
              @if (store.confirmedFloors().length > 1) {
                <mat-form-field appearance="outline" subscriptSizing="dynamic" class="floor"
                  ><mat-label>Floor</mat-label>
                  <mat-select [(ngModel)]="store.drawFloor" name="drawFloor">
                    <mat-option [value]="null">By region</mat-option>
                    @for (a of store.confirmedFloors(); track a.floor_id) {
                      <mat-option [value]="a.floor_id">{{
                        store.floorLabel(a.floor_id)
                      }}</mat-option>
                    }
                  </mat-select>
                </mat-form-field>
              }
              <mat-form-field appearance="outline" subscriptSizing="dynamic"
                ><mat-label>Type</mat-label>
                <mat-select [(ngModel)]="store.unitType" name="unitType">
                  @for (t of unitTypes; track t.value) {
                    <mat-option [value]="t.value">{{ t.label }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
              <mat-form-field appearance="outline" subscriptSizing="dynamic"
                ><mat-label>Code (optional)</mat-label
                ><input matInput [(ngModel)]="store.code" name="code" placeholder="auto"
              /></mat-form-field>
              <mat-form-field appearance="outline" subscriptSizing="dynamic"
                ><mat-label>Label on drawing</mat-label
                ><input matInput [(ngModel)]="store.label" name="label"
              /></mat-form-field>
            </div>
          }
          @if (store.candidates().length) {
            <div class="uf-card uf-stack">
              <div class="uf-form-row">
                <ng-icon name="lucideSparkles" class="lead" />
                <strong
                  >{{ store.candidates().length }} suggested outline{{
                    store.candidates().length === 1 ? '' : 's'
                  }}</strong
                >
                <span class="uf-muted uf-small">dashed on the drawing; click one to select it</span>
                <span class="uf-spacer"></span>
                <button
                  mat-stroked-button
                  [disabled]="store.busy() || store.labelledCount() === 0"
                  (click)="store.acceptLabelled()"
                >
                  <ng-icon name="lucideCheck" /> Accept all {{ store.labelledCount() }} confident
                </button>
                <button mat-button (click)="store.candidates.set([])">Clear suggestions</button>
              </div>
              @if (store.selectedCandidate(); as c) {
                <div class="uf-form-row">
                  <span class="uf-chip uf-tone-info">{{ c.label ?? 'unlabelled' }}</span>
                  <span
                    class="uf-chip"
                    [class.uf-tone-good]="c.confidence >= 0.85"
                    [class.uf-tone-warning]="c.confidence < 0.85"
                    [title]="'How sure the engine is; 85 % and above counts as confident'"
                    >{{ c.confidence * 100 | number: '1.0-0' }} % ·
                    {{ methodLabel(c.method) }}</span
                  >
                  @if (c.printed_area_m2 !== null && c.printed_area_m2 !== undefined) {
                    <span class="uf-muted uf-small"
                      >printed {{ c.printed_area_m2 }} m²
                      @if (c.measured_area_m2 !== null && c.measured_area_m2 !== undefined) {
                        · measured {{ c.measured_area_m2 }} m²
                      }
                    </span>
                  }
                  <span class="uf-muted uf-small">{{
                    c.floor_id
                      ? store.floorLabel(c.floor_id)
                      : store.confirmedFloors().length > 1
                        ? 'outside every region: choose a floor'
                        : ''
                  }}</span>
                  <mat-form-field appearance="outline" subscriptSizing="dynamic"
                    ><mat-label>Type</mat-label>
                    <mat-select [(ngModel)]="store.unitType" name="candType">
                      @for (t of unitTypes; track t.value) {
                        <mat-option [value]="t.value">{{ t.label }}</mat-option>
                      }
                    </mat-select>
                  </mat-form-field>
                  <mat-form-field appearance="outline" subscriptSizing="dynamic"
                    ><mat-label>Code (optional)</mat-label
                    ><input matInput [(ngModel)]="store.code" name="candCode" placeholder="auto"
                  /></mat-form-field>
                  <button
                    mat-flat-button
                    [disabled]="store.busy()"
                    (click)="store.acceptCandidate(c)"
                  >
                    Accept as unit
                  </button>
                  <button mat-button [disabled]="store.busy()" (click)="store.dismissCandidate(c)">
                    Dismiss
                  </button>
                </div>
              }
            </div>
          }
          <div class="viewer">
            <uf-plan-viewer
              [src]="s.raster_url ?? null"
              [width]="s.raster_width ?? 1000"
              [height]="s.raster_height ?? 700"
              [polygons]="store.polygons()"
              [mode]="store.mode()"
              (polygonDrawn)="store.onDrawn($event)"
              (calibrationPicked)="store.calibPts.set($event)"
              (polygonSelected)="store.onSelected($event)"
            />
          </div>
          <uf-sheet-units-table />
        }
      }
    </div>
  `,
  styles: `
    .tools mat-button-toggle ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
    .mode-hint {
      margin-top: -0.5rem;
    }
    .lead {
      color: var(--uf-primary);
      font-size: 1.25rem;
    }
    .floor {
      min-width: 220px;
    }
    .viewer {
      background: var(--uf-surface);
      border: 1px solid var(--uf-border);
      border-radius: var(--uf-radius);
      overflow: hidden;
    }
    .viewer uf-plan-viewer {
      --uf-plan-height: auto;
      --uf-plan-max-height: 82vh;
      --uf-plan-min-height: 320px;
    }
    a ng-icon,
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class SheetPage {
  protected readonly store = inject(SheetStore);
  private readonly routeInfo = inject(RouteInfo);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly sheetId = input.required<string>();
  readonly unitTypes = UNIT_TYPES;
  methodLabel = methodLabel;

  readonly facts = computed<HeaderFact[]>(() => {
    const s = this.store.sheet();
    if (!s) return [];
    const ppm = this.store.pxPerMetre();
    return [
      { domain: 'sheet.assignment', status: s.excluded ? 'excluded' : s.assignment_status },
      {
        domain: 'sheet.calibration',
        status: s.calibration_status,
        value: ppm
          ? `${Math.round(ppm)} px/m${s.calibration_status === 'inherited' ? ' (inherited)' : this.store.calibrationSource() ? ' (from the drawing units)' : ''}`
          : undefined,
      },
      { label: 'Units', value: this.store.units().length },
      { label: 'Draft', value: this.store.draftCount() },
    ];
  });

  constructor() {
    toObservable(this.sheetId).subscribe(() => {
      this.store.init(this.tenantId(), this.projectId(), this.sheetId());
      void this.store.load();
    });
    effect(() => {
      const s = this.store.sheet();
      this.routeInfo.setLeaf(s ? `Page ${s.page_no}` : null);
    });
  }
}
