import { Component, computed, inject } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { PortalApi } from './core/portal-api';
import { SiteStore } from './core/site.store';

@Component({
  selector: 'uf-root',
  imports: [RouterOutlet, RouterLink],
  template: `
    @if (api.previewToken()) {
      <div class="uf-preview" role="status">
        Preview — this version is not visible to buyers yet.
        <button type="button" (click)="exitPreview()">Exit preview</button>
      </div>
    }
    <header class="uf-header">
      <a routerLink="/" class="uf-brand">{{ brandName() }}</a>
      @if (store.site()?.branding?.tagline; as t) { <span class="uf-tagline">{{ t }}</span> }
    </header>
    <main class="uf-main">
      @switch (store.state()) {
        @case ('loading') { <p class="uf-muted uf-center">Loading…</p> }
        @case ('not_configured') {
          <section class="uf-empty">
            <h1>This address is not set up</h1>
            <p>There is no property portal at this address. If you own this domain, finish its setup in Unitforma.</p>
          </section>
        }
        @case ('error') {
          <section class="uf-empty"><h1>Something went wrong</h1><p>{{ store.error() }}</p><button type="button" (click)="store.load()">Try again</button></section>
        }
        @default { <router-outlet /> }
      }
    </main>
    <footer class="uf-footer">
      @if (store.site()?.branding; as b) {
        @if (b.contact_email || b.contact_phone) {
          <p>
            @if (b.contact_email) { <a [href]="'mailto:' + b.contact_email">{{ b.contact_email }}</a> }
            @if (b.contact_phone) { · <a [href]="'tel:' + b.contact_phone">{{ b.contact_phone }}</a> }
            @if (b.website) { · <a [href]="b.website" rel="noopener">{{ b.website }}</a> }
          </p>
        }
        @if (b.legal_text) { <p class="uf-legal">{{ b.legal_text }}</p> }
      }
      <p class="uf-powered">Powered by Unitforma</p>
    </footer>
  `,
})
export class App {
  protected readonly store = inject(SiteStore);
  protected readonly api = inject(PortalApi);
  protected readonly brandName = computed(() => {
    const s = this.store.site();
    return s?.branding?.display_name || s?.tenant.name || 'Unitforma';
  });

  constructor() {
    void this.store.load();
  }

  exitPreview(): void {
    this.api.endPreview();
    location.href = location.pathname;
  }
}
