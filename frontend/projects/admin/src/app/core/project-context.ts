import { Injectable, inject, signal } from '@angular/core';
import { ProjectOut, UnitformaApi, problemMessage } from 'api-client';

/** The project section of the menu and the breadcrumbs follow this (ADR-0009 Decision 2). */
@Injectable({ providedIn: 'root' })
export class ProjectContext {
  private readonly api = inject(UnitformaApi);
  private loadedKey: string | null = null;
  readonly projectId = signal<string | null>(null);
  readonly project = signal<ProjectOut | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  async load(tenantId: string, projectId: string): Promise<void> {
    const key = `${tenantId}/${projectId}`;
    this.projectId.set(projectId);
    if (this.loadedKey === key) return;
    this.loadedKey = key;
    this.project.set(null);
    this.loading.set(true);
    this.error.set(null);
    try {
      const p = await this.api.getProject(tenantId, projectId);
      if (this.loadedKey === key) this.project.set(p);
    } catch (e) {
      this.error.set(problemMessage(e));
      this.loadedKey = null;
    } finally {
      this.loading.set(false);
    }
  }

  /** Pages that change the project header (status, name) push the fresh copy here. */
  set(p: ProjectOut): void {
    this.project.set(p);
  }

  clear(): void {
    this.loadedKey = null;
    this.projectId.set(null);
    this.project.set(null);
  }
}
