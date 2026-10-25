import { Injectable, computed, inject, signal } from '@angular/core';
import { ProjectOut, TenantOut, UnitformaApi, problemMessage } from 'api-client';

/**
 * The tenant a user is working in (ADR-0009 Decision 2). Loaded once per tenant id and shared by
 * the side menu, the breadcrumbs and the page headers; pages keep ownership of the lists they edit.
 */
@Injectable({ providedIn: 'root' })
export class TenantContext {
  private readonly api = inject(UnitformaApi);
  private loadedId: string | null = null;
  readonly tenantId = signal<string | null>(null);
  readonly tenant = signal<TenantOut | null>(null);
  readonly projects = signal<ProjectOut[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly name = computed(() => this.tenant()?.name ?? '');

  /** No-op when this tenant is already loaded, so repeated navigations cost nothing. */
  async load(id: string): Promise<void> {
    this.tenantId.set(id);
    if (this.loadedId === id) return;
    this.loadedId = id;
    this.tenant.set(null);
    this.projects.set([]);
    await this.reload();
  }

  async reload(): Promise<void> {
    const id = this.tenantId();
    if (!id) return;
    this.loading.set(true);
    this.error.set(null);
    try {
      const [t, p] = await Promise.all([this.api.getTenant(id), this.api.listProjects(id)]);
      if (this.tenantId() !== id) return;
      this.tenant.set(t);
      this.projects.set(p);
    } catch (e) {
      this.error.set(problemMessage(e));
      this.loadedId = null;
    } finally {
      this.loading.set(false);
    }
  }

  /** Called by pages that create or rename projects so the menu's project list follows. */
  async refreshProjects(): Promise<void> {
    const id = this.tenantId();
    if (!id) return;
    try {
      this.projects.set(await this.api.listProjects(id));
    } catch {
      /* the menu keeps the previous list */
    }
  }

  clear(): void {
    this.loadedId = null;
    this.tenantId.set(null);
    this.tenant.set(null);
    this.projects.set([]);
  }
}
