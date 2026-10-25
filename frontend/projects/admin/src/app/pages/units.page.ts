import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { LineageOut, UnitOut, UnitformaApi, problemMessage } from 'api-client';
import {
  EmptyStateComponent,
  HeaderFact,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
  ago,
  labelOf,
  statusOf,
  whenShort,
} from 'ui';

/** Project units with their three states, areas and the lineage log (plan §3.2 unit identity). */
@Component({
  selector: 'uf-units-page',
  imports: [
    FormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    RouterLink,
    NgIcon,
    PageHeaderComponent,
    SectionCardComponent,
    StatusChipComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header title="Units & lineage" icon="lucideLayers" [facts]="facts()">
        <ng-container actions>
          <a mat-stroked-button routerLink="../inventory"
            ><ng-icon name="lucideTable" /> Inventory &amp; prices</a
          >
        </ng-container>
      </uf-page-header>
      @if (error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }

      @if (units().length) {
        <div class="uf-filterbar">
          <mat-form-field appearance="outline" subscriptSizing="dynamic" class="search"
            ><ng-icon matPrefix name="lucideSearch" /><input
              matInput
              [ngModel]="query()"
              (ngModelChange)="query.set($event)"
              placeholder="Code…"
              aria-label="Search units"
          /></mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>Type</mat-label>
            <mat-select [ngModel]="type()" (ngModelChange)="type.set($event)"
              ><mat-option [value]="null">All</mat-option>
              @for (t of types(); track t) {
                <mat-option [value]="t">{{ labelOf('unit_type', t) }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>Verification</mat-label>
            <mat-select [ngModel]="verification()" (ngModelChange)="verification.set($event)"
              ><mat-option [value]="null">All</mat-option>
              @for (v of verifications(); track v) {
                <mat-option [value]="v">{{ labelOf('unit.verification', v) }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>Publication</mat-label>
            <mat-select [ngModel]="publication()" (ngModelChange)="publication.set($event)"
              ><mat-option [value]="null">All</mat-option>
              @for (v of publications(); track v) {
                <mat-option [value]="v">{{ labelOf('unit.publication', v) }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <span class="uf-count">{{ shown().length }} of {{ units().length }}</span>
        </div>
        <div class="uf-card" style="padding: 0">
          <table class="uf-plain">
            <thead>
              <tr>
                <th>Code</th>
                <th>Type</th>
                <th>Lifecycle</th>
                <th>Verification</th>
                <th>Publication</th>
                <th>Areas</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (u of shown(); track u.id) {
                <tr>
                  <td>
                    <strong>{{ u.code }}</strong>
                  </td>
                  <td>
                    <span class="uf-chip"
                      ><ng-icon [name]="statusOf('unit_type', u.unit_type).icon" />{{
                        labelOf('unit_type', u.unit_type)
                      }}</span
                    >
                  </td>
                  <td><uf-status-chip domain="unit.lifecycle" [value]="u.lifecycle_status" /></td>
                  <td>
                    <uf-status-chip domain="unit.verification" [value]="u.verification_status" />
                  </td>
                  <td>
                    <uf-status-chip domain="unit.publication" [value]="u.publication_status" />
                  </td>
                  <td class="areas">
                    @for (a of u.areas; track a.id) {
                      <span class="area" [title]="a.source + ', ' + a.verification_status"
                        ><strong>{{ a.value_m2 }} m²</strong>
                        <span class="uf-muted">{{ a.area_type }}</span></span
                      >
                    } @empty {
                      <span class="uf-muted">—</span>
                    }
                  </td>
                  <td class="actions">
                    <a mat-button [routerLink]="['../inventory', u.id]"
                      >Prices <ng-icon name="lucideArrowRight"
                    /></a>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="7">
                    <uf-empty-state
                      icon="lucideListFilter"
                      title="Nothing matches these filters"
                      [compact]="true"
                    />
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else if (loaded()) {
        <uf-empty-state
          icon="lucideLayers"
          title="No units yet"
          text="Units are created when a mapped sheet is approved. Upload a floor plan under Documents, draw or accept the unit outlines and approve."
        >
          <a mat-flat-button routerLink="../documents">Open Documents</a>
        </uf-empty-state>
      }

      <uf-section-card
        title="Lineage"
        icon="lucideHistory"
        [count]="lineage().length"
        [summary]="lineage()[0] ? 'last event ' + ago(lineage()[0].decided_at) : 'no events yet'"
        storageKey="units-lineage"
      >
        <p class="uf-hint">
          The history of identities: units are never deleted or re-keyed. Relabels, splits, merges
          and removals are recorded here with the units before and after.
        </p>
        <ul class="uf-timeline">
          @for (e of lineage(); track e.id) {
            <li [class]="'is-' + statusOf('lineage', e.event_type).tone">
              <div class="uf-timeline__when">{{ when(e.decided_at) }}</div>
              <div>
                <uf-status-chip domain="lineage" [value]="e.event_type" /> {{ e.note ?? '' }}
                <span class="uf-muted uf-small"
                  >{{ e.from_unit_ids.length }} → {{ e.to_unit_ids.length }} unit{{
                    e.to_unit_ids.length === 1 ? '' : 's'
                  }}</span
                >
              </div>
            </li>
          } @empty {
            <li class="uf-muted">No lineage events yet.</li>
          }
        </ul>
      </uf-section-card>
    </div>
  `,
  styles: `
    .search {
      min-width: 200px;
    }
    .search ng-icon {
      margin: 0 0.25rem 0 0.5rem;
      color: var(--uf-muted);
    }
    .areas {
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
    }
    .area {
      white-space: nowrap;
      font-size: 0.9rem;
    }
    .actions {
      text-align: right;
      white-space: nowrap;
    }
    a ng-icon,
    button ng-icon {
      vertical-align: -0.15em;
    }
  `,
})
export class UnitsPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly units = signal<UnitOut[]>([]);
  readonly lineage = signal<LineageOut[]>([]);
  readonly loaded = signal(false);
  readonly error = signal<string | null>(null);
  readonly query = signal('');
  readonly type = signal<string | null>(null);
  readonly verification = signal<string | null>(null);
  readonly publication = signal<string | null>(null);
  readonly types = computed(() => [...new Set(this.units().map((u) => u.unit_type))].sort());
  readonly verifications = computed(() =>
    [...new Set(this.units().map((u) => u.verification_status))].sort(),
  );
  readonly publications = computed(() =>
    [...new Set(this.units().map((u) => u.publication_status))].sort(),
  );
  readonly shown = computed(() => {
    const q = this.query().trim().toLowerCase();
    return this.units().filter(
      (u) =>
        (!q || u.code.toLowerCase().includes(q)) &&
        (!this.type() || u.unit_type === this.type()) &&
        (!this.verification() || u.verification_status === this.verification()) &&
        (!this.publication() || u.publication_status === this.publication()),
    );
  });
  readonly facts = computed<HeaderFact[]>(() => {
    const u = this.units();
    const n = (f: (x: UnitOut) => boolean) => u.filter(f).length;
    return [
      { label: 'Units', value: u.length },
      {
        domain: 'unit.verification',
        status: 'verified',
        value: `${n((x) => x.verification_status === 'verified')} verified`,
      },
      {
        domain: 'unit.publication',
        status: 'published',
        value: `${n((x) => x.publication_status === 'published')} public`,
      },
      {
        domain: 'unit.lifecycle',
        status: 'removed',
        value: `${n((x) => x.lifecycle_status === 'removed')} removed`,
      },
    ];
  });
  labelOf = labelOf;
  statusOf = statusOf;
  when = whenShort;
  ago = ago;

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  async load(): Promise<void> {
    try {
      const [u, l] = await Promise.all([
        this.api.listUnits(this.tenantId(), this.projectId()),
        this.api.projectLineage(this.tenantId(), this.projectId()),
      ]);
      this.units.set(u);
      this.lineage.set(l);
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.loaded.set(true);
    }
  }
}
