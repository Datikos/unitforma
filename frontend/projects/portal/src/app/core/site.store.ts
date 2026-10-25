import { Injectable, inject, signal } from '@angular/core';
import { Branding, PortalApi, ProjectDoc, SiteOut, problemOf } from './portal-api';

export type SiteState = 'loading' | 'ready' | 'not_configured' | 'error';

/** Host-level state: site summary, branding (CSS variables) and cached project snapshots. */
@Injectable({ providedIn: 'root' })
export class SiteStore {
  private readonly api = inject(PortalApi);
  readonly state = signal<SiteState>('loading');
  readonly site = signal<SiteOut | null>(null);
  readonly error = signal<string | null>(null);
  private readonly projects = new Map<string, Promise<ProjectDoc>>();

  async load(): Promise<void> {
    try {
      const s = await this.api.site();
      this.site.set(s);
      applyBranding(s.branding);
      document.title = s.branding.display_name || s.tenant.name;
      this.state.set('ready');
    } catch (e) {
      const p = problemOf(e);
      if (p.status === 404 && p.type?.endsWith('portal-not-configured')) this.state.set('not_configured');
      else {
        this.error.set(p.title ?? 'The portal is temporarily unavailable');
        this.state.set('error');
      }
    }
  }

  project(slug: string): Promise<ProjectDoc> {
    let p = this.projects.get(slug);
    if (!p) {
      p = this.api.project(slug).then((doc) => {
        applyBranding(doc.branding);
        return doc;
      });
      p.catch(() => this.projects.delete(slug));
      this.projects.set(slug, p);
    }
    return p;
  }
}

const HEX = /^#[0-9a-f]{6}$/i;

/** Tenant palette as CSS custom properties (plan §11.4); values were allow-listed by the backend. */
export function applyBranding(b: Branding | null | undefined): void {
  const root = document.documentElement.style;
  if (b?.primary_color && HEX.test(b.primary_color)) root.setProperty('--uf-primary', b.primary_color);
  if (b?.accent_color && HEX.test(b.accent_color)) root.setProperty('--uf-accent', b.accent_color);
}
