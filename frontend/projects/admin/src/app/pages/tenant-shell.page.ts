import { Component, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { MatTabsModule } from '@angular/material/tabs';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { TenantOut, UnitformaApi, problemMessage } from 'api-client';

@Component({
  selector: 'uf-tenant-shell-page',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, MatTabsModule],
  template: `
    <div class="uf-page">
      @if (tenant(); as t) {
        <div class="uf-page-header"><h1>{{ t.name }}</h1><span class="uf-muted">{{ t.slug }}.unitforma.com</span></div>
      } @else if (error()) {
        <p class="uf-error">{{ error() }}</p>
      }
      <nav mat-tab-nav-bar [tabPanel]="panel">
        <a mat-tab-link routerLink="projects" routerLinkActive #p="routerLinkActive" [active]="p.isActive">Projects</a>
        <a mat-tab-link routerLink="members" routerLinkActive #m="routerLinkActive" [active]="m.isActive">Members</a>
        <a mat-tab-link routerLink="audit" routerLinkActive #a="routerLinkActive" [active]="a.isActive">Audit log</a>
      </nav>
      <mat-tab-nav-panel #panel><router-outlet /></mat-tab-nav-panel>
    </div>
  `,
})
export class TenantShellPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly tenant = signal<TenantOut | null>(null);
  readonly error = signal<string | null>(null);

  constructor() {
    toObservable(this.tenantId).subscribe((id) => void this.load(id));
  }

  private async load(id: string): Promise<void> {
    try {
      this.tenant.set(await this.api.getTenant(id));
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }
}
