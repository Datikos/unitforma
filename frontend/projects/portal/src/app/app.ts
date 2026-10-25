import { Component, inject } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { EmptyStateComponent, UF_ICONS } from 'ui';
import { PortalHeaderComponent } from './ui/portal-header.component';
import { PortalApi } from './core/portal-api';
import { SiteStore } from './core/site.store';

@Component({
  selector: 'uf-root',
  imports: [RouterOutlet, RouterLink, NgIcon, PortalHeaderComponent, EmptyStateComponent],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    @if (api.previewToken()) {
      <div class="uf-preview" role="status">
        Preview — this version is not visible to buyers yet.
        <button type="button" (click)="exitPreview()">Exit preview</button>
      </div>
    }
    <uf-portal-header />
    <main class="uf-main">
      @switch (store.state()) {
        @case ('loading') {
          <p class="uf-muted uf-center">Loading…</p>
        }
        @case ('not_configured') {
          <uf-empty-state
            icon="lucideGlobe"
            title="This address is not set up"
            text="There is no property portal at this address. If you own this domain, finish its setup in Unitforma."
          />
        }
        @case ('error') {
          <uf-empty-state icon="lucideCircleX" title="Something went wrong" [text]="store.error()"
            ><button type="button" (click)="store.load()">
              <ng-icon name="lucideRefreshCw" /> Try again
            </button></uf-empty-state
          >
        }
        @default {
          <router-outlet />
        }
      }
    </main>
    <footer class="uf-footer">
      @if (store.site()?.branding; as b) {
        @if (b.contact_email || b.contact_phone || b.website) {
          <p class="uf-footer__row">
            @if (b.contact_email) {
              <a [href]="'mailto:' + b.contact_email"
                ><ng-icon name="lucideMail" /> {{ b.contact_email }}</a
              >
            }
            @if (b.contact_phone) {
              <a [href]="'tel:' + b.contact_phone"
                ><ng-icon name="lucidePhone" /> {{ b.contact_phone }}</a
              >
            }
            @if (b.website) {
              <a [href]="b.website" rel="noopener"
                ><ng-icon name="lucideGlobe" /> {{ b.website }}</a
              >
            }
          </p>
        }
        @if (b.legal_text) {
          <p class="uf-legal">{{ b.legal_text }}</p>
        }
      }
      <p class="uf-footer__row">
        <a routerLink="/how-to-use"><ng-icon name="lucideCircleHelp" /> How to use this portal</a
        ><span class="uf-powered">Powered by Unitforma</span>
      </p>
    </footer>
  `,
})
export class App {
  protected readonly store = inject(SiteStore);
  protected readonly api = inject(PortalApi);
  constructor() {
    void this.store.load();
  }

  exitPreview(): void {
    this.api.endPreview();
    location.href = location.pathname;
  }
}
