import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { DocumentOut, ProposalOut, UnitformaApi, problemMessage } from 'api-client';
import {
  EmptyStateComponent,
  HeaderFact,
  PageHeaderComponent,
  StatusChipComponent,
  UF_ICONS,
  ago,
  whenShort,
} from 'ui';

const KINDS = ['matched', 'relabelled', 'split', 'merged', 'new', 'missing', 'complex'];

/** Revision diff proposals of a project (plan §13.3): one per processed revision of a mapped document. */
@Component({
  selector: 'uf-proposals-page',
  imports: [
    MatButtonModule,
    RouterLink,
    NgIcon,
    PageHeaderComponent,
    StatusChipComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header title="Revision diffs" icon="lucideGitCompare" [facts]="facts()">
        <p subtitle class="uf-hint">
          When a new revision of a mapped document is processed, the worker compares its line work
          with the current unit boundaries and proposes relabels, splits, merges, new and missing
          units. Nothing changes until a reviewer decides.
        </p>
      </uf-page-header>
      @if (error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }
      <div class="uf-grid3">
        @for (p of proposals(); track p.id) {
          <a class="uf-card card uf-quiet" [routerLink]="[p.id]">
            <div class="card__head">
              <strong>{{ docTitle(p.document_id) }}</strong>
              <uf-status-chip domain="proposal.status" [value]="p.status" />
            </div>
            <div class="uf-muted uf-small">
              revision {{ p.new_revision_id.slice(0, 8) }} · {{ when(p.created_at) }} ·
              {{ ago(p.created_at) }}
            </div>
            <div class="uf-chips">
              @for (k of kinds(p); track k.kind) {
                <uf-status-chip
                  domain="proposal.kind"
                  [value]="k.kind"
                  [label]="k.count + ' ' + k.kind"
                />
              } @empty {
                <span class="uf-muted uf-small">no changes</span>
              }
            </div>
            <span class="card__go"
              >{{ p.status === 'open' ? 'Review' : 'Open' }} <ng-icon name="lucideArrowRight"
            /></span>
          </a>
        } @empty {
          @if (loaded()) {
            <uf-empty-state
              icon="lucideGitCompare"
              title="No revision diffs yet"
              text="Upload a new revision of a document whose pages already have units. Once processed, its differences appear here for review."
            >
              <a mat-stroked-button routerLink="../documents">Open Documents</a>
            </uf-empty-state>
          }
        }
      </div>
    </div>
  `,
  styles: `
    .card {
      display: grid;
      gap: 0.5rem;
      align-content: start;
      transition:
        box-shadow 0.15s,
        border-color 0.15s;
    }
    .card:hover {
      box-shadow: var(--uf-shadow-lg);
      border-color: var(--uf-primary);
    }
    .card__head {
      display: flex;
      justify-content: space-between;
      gap: 0.5rem;
      align-items: center;
    }
    .card__go {
      color: var(--uf-primary);
      font-weight: 600;
      font-size: 0.85rem;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
    }
  `,
})
export class ProposalsPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly proposals = signal<ProposalOut[]>([]);
  readonly docs = signal<DocumentOut[]>([]);
  readonly loaded = signal(false);
  readonly error = signal<string | null>(null);
  readonly facts = computed<HeaderFact[]>(() => [
    { label: 'Diffs', value: this.proposals().length },
    {
      domain: 'proposal.status',
      status: 'open',
      value: `${this.proposals().filter((p) => p.status === 'open').length} open`,
    },
  ]);
  when = whenShort;
  ago = ago;

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  async load(): Promise<void> {
    try {
      const [p, d] = await Promise.all([
        this.api.listProposals(this.tenantId(), this.projectId()),
        this.api.listDocuments(this.tenantId(), this.projectId()),
      ]);
      this.proposals.set(p);
      this.docs.set(d);
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.loaded.set(true);
    }
  }

  docTitle(id: string): string {
    return this.docs().find((d) => d.id === id)?.title ?? 'Document';
  }

  kinds(p: ProposalOut): { kind: string; count: number }[] {
    const s = p.summary as Record<string, number>;
    return KINDS.filter((k) => s[k]).map((k) => ({ kind: k, count: s[k] }));
  }
}
