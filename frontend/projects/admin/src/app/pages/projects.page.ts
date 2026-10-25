import { Component, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatListModule } from '@angular/material/list';
import { RouterLink } from '@angular/router';
import { ProjectOut, UnitformaApi, problemMessage } from 'api-client';

@Component({
  selector: 'uf-projects-page',
  imports: [FormsModule, MatCardModule, MatFormFieldModule, MatInputModule, MatButtonModule, MatListModule, RouterLink],
  template: `
    <div class="uf-page">
      <mat-card appearance="outlined">
        <mat-card-header><mat-card-title>New project</mat-card-title></mat-card-header>
        <mat-card-content class="uf-form-row">
          <mat-form-field appearance="outline"><mat-label>Slug</mat-label><input matInput [(ngModel)]="slug" name="slug" /></mat-form-field>
          <mat-form-field appearance="outline"><mat-label>Name</mat-label><input matInput [(ngModel)]="name" name="name" /></mat-form-field>
          <button mat-flat-button [disabled]="busy()" (click)="create()">Create</button>
        </mat-card-content>
        @if (error()) { <mat-card-footer><p class="uf-error">{{ error() }}</p></mat-card-footer> }
      </mat-card>
      <mat-nav-list>
        @for (p of projects(); track p.id) {
          <a mat-list-item [routerLink]="[p.id]">
            <span matListItemTitle>{{ p.name }}</span>
            <span matListItemLine>{{ p.slug }} · {{ p.status }} · {{ p.currency }}</span>
          </a>
        } @empty {
          <p class="uf-muted">No projects yet.</p>
        }
      </mat-nav-list>
    </div>
  `,
  styles: `.uf-form-row { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }`,
})
export class ProjectsPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projects = signal<ProjectOut[]>([]);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  slug = '';
  name = '';

  constructor() {
    toObservable(this.tenantId).subscribe(() => void this.load());
  }

  async load(): Promise<void> {
    try {
      this.projects.set(await this.api.listProjects(this.tenantId()));
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  async create(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.createProject(this.tenantId(), { slug: this.slug, name: this.name });
      this.slug = this.name = '';
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}
