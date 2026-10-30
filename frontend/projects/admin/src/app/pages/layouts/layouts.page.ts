import { Component, computed, effect, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  EmptyStateComponent,
  HeaderFact,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
} from 'ui';
import { MediaListComponent, MediaUpload } from '../../sales/media-list.component';
import { RenderGenerate, RenderListComponent } from '../../sales/render-list.component';
import {
  LayoutForm,
  blankLayoutForm,
  formOf,
  layoutSummary,
  orderLayouts,
  registryFacts,
  validateCode,
} from './layouts.model';
import { LayoutsStore } from './layouts.store';

/**
 * The layout registry of a project (ADR-0022 Decision 6): one card per plan type with its
 * linked units, media and generated render, a create form, rename and delete.
 */
@Component({
  selector: 'uf-layouts-page',
  imports: [
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    NgIcon,
    PageHeaderComponent,
    SectionCardComponent,
    StatusChipComponent,
    EmptyStateComponent,
    MediaListComponent,
    RenderListComponent,
  ],
  providers: [LayoutsStore],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header title="Layouts & renders" icon="lucideLayoutGrid" [facts]="facts()">
        <ng-container actions
          ><a mat-stroked-button routerLink="../inventory"
            ><ng-icon name="lucideTable" /> Inventory</a
          ></ng-container
        >
      </uf-page-header>
      @if (store.error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }

      <div class="layout" [class.layout--split]="!!store.selected()">
        <div class="uf-stack list">
          <uf-section-card
            title="New layout"
            icon="lucidePlus"
            summary="one code per plan type"
            storageKey="layouts-new"
            [open]="!store.layouts().length"
          >
            <div class="uf-form-row">
              <mat-form-field appearance="outline" subscriptSizing="dynamic" class="code"
                ><mat-label>Code</mat-label
                ><input
                  matInput
                  [ngModel]="draft().code"
                  (ngModelChange)="setDraft('code', $event)"
                  name="newCode"
                  maxlength="40"
                  placeholder="L1"
                  required
              /></mat-form-field>
              <mat-form-field appearance="outline" subscriptSizing="dynamic" class="name"
                ><mat-label>Name (optional)</mat-label
                ><input
                  matInput
                  [ngModel]="draft().name"
                  (ngModelChange)="setDraft('name', $event)"
                  name="newName"
                  maxlength="120"
                  placeholder="Two rooms, corner"
              /></mat-form-field>
              <button
                mat-flat-button
                [disabled]="store.busy() || !!draftError()"
                [title]="draftError() ?? ''"
                (click)="create()"
              >
                <ng-icon name="lucidePlus" /> Create
              </button>
            </div>
            <p class="uf-hint">
              The code is what the inventory grid and the unit form pick; buyers see it next to the
              shared renders. Link units to it in the inventory (Layout column) or on the unit page.
            </p>
          </uf-section-card>

          @for (l of ordered(); track l.id) {
            <button
              type="button"
              class="card"
              [class.card--selected]="l.id === store.selectedId()"
              [class.card--proposed]="l.status === 'proposed'"
              (click)="store.select(l.id)"
            >
              @if (l.cover_url) {
                <img [src]="l.cover_url" alt="" class="card__cover" loading="lazy" />
              } @else {
                <div class="card__cover card__cover--empty"><ng-icon name="lucideImage" /></div>
              }
              <div class="card__body">
                <div class="uf-row">
                  <strong class="card__code">{{ l.code }}</strong>
                  @if (l.name) {
                    <span class="uf-muted">{{ l.name }}</span>
                  }
                  <span class="uf-spacer"></span>
                  @if (l.status === 'proposed') {
                    <uf-status-chip domain="layout" [value]="l.status" />
                  } @else if (!l.public_media_count) {
                    <span class="uf-chip uf-tone-warning" title="Nothing reaches the portal yet"
                      ><ng-icon name="lucideTriangleAlert" />no public media</span
                    >
                  }
                </div>
                <div class="uf-muted small">{{ summary(l) }}</div>
                <div class="chips">
                  @for (u of l.units; track u.unit_id) {
                    <uf-status-chip
                      domain="availability"
                      [value]="u.availability"
                      [label]="u.code"
                    />
                  } @empty {
                    <span class="uf-muted small">No unit linked yet.</span>
                  }
                </div>
              </div>
            </button>
          } @empty {
            @if (store.loaded()) {
              <uf-empty-state
                icon="lucideLayoutGrid"
                title="No layouts yet"
                text="Create one per plan type above, then link units to it in the inventory. Each layout holds the renders every linked unit shows."
              />
            }
          }
        </div>

        <div class="uf-stack detail">
          @if (store.selected(); as l) {
            <uf-section-card
              [title]="'Layout ' + l.code"
              icon="lucideLayoutGrid"
              [summary]="l.name ?? 'no name'"
              [tone]="l.status === 'proposed' ? 'warning' : null"
              storageKey="layouts-detail"
            >
              @if (l.status === 'proposed') {
                <div class="uf-alert uf-alert--info proposed" role="status">
                  <ng-icon name="lucideSparkles" />
                  <span
                    >The setup solver grouped these {{ l.units.length }} units: their outlines
                    coincide
                    @if (l.match?.['iou_min']; as iou) {
                      (overlap {{ iou }} or better)
                    }
                    @if (l.match?.['mirror_of']; as base) {
                      as the mirror image of {{ base }}
                    }
                    . Until you confirm it, the layout owns no media and buyers never see it; if the
                    grouping is wrong, delete it and the units keep their own data.</span
                  >
                  <span class="uf-spacer"></span>
                  <button mat-flat-button [disabled]="store.busy()" (click)="store.confirm(l)">
                    <ng-icon name="lucideCheck" /> Confirm plan type
                  </button>
                </div>
              }
              <div class="uf-form-row">
                <mat-form-field appearance="outline" subscriptSizing="dynamic" class="code"
                  ><mat-label>Code</mat-label
                  ><input
                    matInput
                    [ngModel]="edit().code"
                    (ngModelChange)="setEdit('code', $event)"
                    name="editCode"
                    maxlength="40"
                /></mat-form-field>
                <mat-form-field appearance="outline" subscriptSizing="dynamic" class="name"
                  ><mat-label>Name</mat-label
                  ><input
                    matInput
                    [ngModel]="edit().name"
                    (ngModelChange)="setEdit('name', $event)"
                    name="editName"
                    maxlength="120"
                /></mat-form-field>
                <button
                  mat-flat-button
                  [disabled]="store.busy() || !editChanged() || !!editError()"
                  [title]="editError() ?? ''"
                  (click)="store.rename(l, edit())"
                >
                  <ng-icon name="lucideCheck" /> Save
                </button>
                <span class="uf-spacer"></span>
                <button mat-button [disabled]="store.busy()" (click)="store.remove(l)">
                  <ng-icon name="lucideTrash2" /> Delete
                </button>
              </div>
              @if (editChanged() && edit().code !== l.code) {
                <p class="uf-hint">Renaming the code updates every linked unit.</p>
              }
              <p class="uf-field-note">
                Units:
                @for (u of l.units; track u.unit_id; let last = $last) {
                  <a [routerLink]="['../inventory', u.unit_id]">{{ u.code }}</a
                  ><span class="uf-muted"> ({{ u.building_code }} · floor {{ u.floor_level }})</span
                  >{{ last ? '' : ', ' }}
                } @empty {
                  none linked;
                  <a routerLink="../inventory">set the Layout column in the inventory</a>
                }
              </p>
            </uf-section-card>

            <uf-media-list
              [media]="store.media()"
              [busy]="store.busy()"
              [title]="'Media of ' + l.code"
              storageKey="layouts-media"
              hint="Public files reach every linked unit on the portal with the next publication, after the unit's own media; AI-generated ones carry a label."
              emptyText="Upload the renders or photos this plan type shares; or generate a 3D plan render below."
              (upload)="onUpload($event)"
              (patch)="store.patchMedia($event.m, $event.body)"
              (move)="store.move($event.i, $event.delta)"
              (remove)="store.removeMedia($event)"
            />

            <uf-render-list
              [renders]="store.renders()"
              [busy]="store.busy()"
              mode="layout"
              [choices]="members()"
              hint="One furnished 3D view for the whole plan type, cropped from a linked unit's outline; private until approved, then labelled and shown on every linked unit."
              storageKey="layouts-renders"
              (generate)="onGenerate($event)"
              (approve)="store.approveRender($event)"
              (reject)="store.rejectRender($event)"
            />
          } @else if (store.layouts().length) {
            <uf-empty-state
              icon="lucideMousePointer"
              title="Pick a layout"
              text="Its units, media and generated render open here."
              [compact]="true"
            />
          }
        </div>
      </div>
    </div>
  `,
  styles: `
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 1rem;
      align-items: start;
    }
    .layout--split {
      grid-template-columns: minmax(18rem, 2fr) minmax(0, 3fr);
    }
    @media (max-width: 1100px) {
      .layout--split {
        grid-template-columns: 1fr;
      }
    }
    .code {
      flex: 0 1 9rem;
    }
    .name {
      flex: 1 1 11rem;
    }
    .card {
      display: grid;
      grid-template-columns: 7rem 1fr;
      gap: 0.75rem;
      width: 100%;
      text-align: left;
      font: inherit;
      color: inherit;
      background: var(--uf-surface);
      border: 1px solid var(--uf-border);
      border-radius: var(--uf-radius);
      padding: 0.6rem;
      cursor: pointer;
    }
    .card:hover {
      border-color: var(--uf-border-strong);
    }
    .card--selected {
      border-color: var(--uf-primary);
      box-shadow: 0 0 0 2px color-mix(in srgb, var(--uf-primary) 25%, transparent);
    }
    .card--proposed {
      border-left: 4px solid var(--uf-warning, #d97706);
    }
    .proposed {
      display: flex;
      gap: 0.5rem;
      align-items: center;
      flex-wrap: wrap;
    }
    .card__cover {
      width: 7rem;
      aspect-ratio: 4 / 3;
      object-fit: cover;
      border-radius: var(--uf-radius-sm);
      background: var(--uf-surface-2);
    }
    .card__cover--empty {
      display: grid;
      place-items: center;
      color: var(--uf-text-muted);
    }
    .card__body {
      display: grid;
      gap: 0.3rem;
      min-width: 0;
    }
    .card__code {
      font-size: 1.05rem;
    }
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 0.3rem;
    }
    .small {
      font-size: 0.85rem;
    }
    a ng-icon,
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class LayoutsPage {
  protected readonly store = inject(LayoutsStore);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();

  readonly draft = signal<LayoutForm>(blankLayoutForm());
  readonly edit = signal<LayoutForm>(blankLayoutForm());
  readonly draftError = computed(() => validateCode(this.draft().code, this.store.layouts()));
  readonly editError = computed(() => {
    const l = this.store.selected();
    return l ? validateCode(this.edit().code, this.store.layouts(), l.id) : null;
  });
  readonly editChanged = computed(() => {
    const l = this.store.selected();
    const e = this.edit();
    return !!l && (e.code.trim() !== l.code || e.name.trim() !== (l.name ?? ''));
  });
  readonly members = computed(() =>
    (this.store.selected()?.units ?? []).map((u) => ({ id: u.unit_id, code: u.code })),
  );
  readonly ordered = computed(() => orderLayouts(this.store.layouts()));
  readonly facts = computed<HeaderFact[]>(() => {
    const f = registryFacts(this.store.layouts());
    return [
      { label: 'layouts', value: f.layouts, icon: 'lucideLayoutGrid' },
      ...(f.proposed
        ? [{ label: 'proposed, waiting for you', value: f.proposed, icon: 'lucideSparkles' }]
        : []),
      { label: 'linked units', value: f.linked, icon: 'lucideLayers' },
      {
        label: 'without public media',
        value: f.withoutMedia,
        icon: f.withoutMedia ? 'lucideTriangleAlert' : 'lucideCircleCheck',
      },
    ];
  });
  summary = layoutSummary;

  constructor() {
    toObservable(this.projectId).subscribe(() => {
      this.store.init(this.tenantId(), this.projectId());
      void this.store.load();
    });
    // the edit form follows the selection (and a rename that just landed)
    effect(() => {
      const l = this.store.selected();
      this.edit.set(l ? formOf(l) : blankLayoutForm());
    });
  }

  setDraft<K extends keyof LayoutForm>(k: K, v: string): void {
    this.draft.update((d) => ({ ...d, [k]: v }));
  }

  setEdit<K extends keyof LayoutForm>(k: K, v: string): void {
    this.edit.update((d) => ({ ...d, [k]: v }));
  }

  async create(): Promise<void> {
    if (await this.store.create(this.draft())) this.draft.set(blankLayoutForm());
  }

  onUpload(u: MediaUpload): Promise<boolean> {
    return this.store.upload(u.file, u.kind, u.isPublic, u.ai);
  }

  onGenerate(g: RenderGenerate): Promise<boolean> {
    return this.store.requestRender(g.note, g.withId);
  }
}
