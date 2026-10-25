import { SlicePipe } from '@angular/common';
import { Component, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { RouterLink } from '@angular/router';
import { DocumentOut, ProposalOut, UnitformaApi, problemMessage } from 'api-client';

/** Revision diff proposals of a project (plan §13.3): one per processed revision of a mapped document. */
@Component({
  selector: 'uf-proposals-page',
  imports: [SlicePipe, MatCardModule, MatButtonModule, RouterLink],
  template: `
    <div class="uf-page">
      <div class="uf-page-header"><h2>Revision diffs</h2><a mat-stroked-button [routerLink]="['..']">Back to project</a></div>
      @if (error()) { <p class="uf-error">{{ error() }}</p> }
      <p class="uf-muted">
        When a new revision of a mapped document is processed, the worker compares its line work with the current unit
        boundaries and proposes relabels, splits, merges, new and missing units. Nothing changes until a reviewer decides.
      </p>
      @for (p of proposals(); track p.id) {
        <mat-card appearance="outlined">
          <mat-card-header>
            <mat-card-title>{{ docTitle(p.document_id) }} · revision {{ p.new_revision_id | slice: 0 : 8 }}</mat-card-title>
            <mat-card-subtitle>{{ p.created_at | slice: 0 : 16 }} · {{ p.status }} · {{ summary(p) }}</mat-card-subtitle>
          </mat-card-header>
          <mat-card-actions>
            <a mat-button [routerLink]="[p.id]">{{ p.status === 'open' ? 'Review' : 'Open' }}</a>
          </mat-card-actions>
        </mat-card>
      } @empty { <p class="uf-muted">No revision diffs yet. Upload a new revision of a document whose pages have units.</p> }
    </div>
  `,
})
export class ProposalsPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly proposals = signal<ProposalOut[]>([]);
  readonly docs = signal<DocumentOut[]>([]);
  readonly error = signal<string | null>(null);

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  async load(): Promise<void> {
    try {
      const [p, d] = await Promise.all([this.api.listProposals(this.tenantId(), this.projectId()), this.api.listDocuments(this.tenantId(), this.projectId())]);
      this.proposals.set(p);
      this.docs.set(d);
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  docTitle(id: string): string {
    return this.docs().find((d) => d.id === id)?.title ?? 'Document';
  }

  summary(p: ProposalOut): string {
    const s = p.summary as Record<string, number>;
    return ['matched', 'relabelled', 'split', 'merged', 'new', 'missing', 'complex']
      .filter((k) => s[k])
      .map((k) => `${s[k]} ${k}`)
      .join(', ') || 'no changes';
  }
}
