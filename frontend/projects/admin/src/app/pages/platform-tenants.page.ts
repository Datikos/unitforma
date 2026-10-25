import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';
import { TenantOut, UnitformaApi, problemMessage } from 'api-client';

@Component({
  selector: 'uf-platform-tenants-page',
  imports: [FormsModule, MatCardModule, MatFormFieldModule, MatInputModule, MatButtonModule, MatTableModule, RouterLink],
  template: `
    <div class="uf-page">
      <div class="uf-page-header"><h1>Tenants</h1></div>
      <mat-card appearance="outlined">
        <mat-card-header><mat-card-title>Create a tenant</mat-card-title></mat-card-header>
        <mat-card-content class="uf-form-row">
          <mat-form-field appearance="outline"><mat-label>Slug (subdomain)</mat-label><input matInput [(ngModel)]="slug" name="slug" /></mat-form-field>
          <mat-form-field appearance="outline"><mat-label>Name</mat-label><input matInput [(ngModel)]="name" name="name" /></mat-form-field>
          <mat-form-field appearance="outline"><mat-label>First admin email</mat-label><input matInput type="email" [(ngModel)]="adminEmail" name="adminEmail" /></mat-form-field>
          <button mat-flat-button [disabled]="busy()" (click)="create()">Create</button>
        </mat-card-content>
        @if (error()) { <mat-card-footer><p class="uf-error">{{ error() }}</p></mat-card-footer> }
        @if (lastInviteUrl()) { <mat-card-footer><p>Invitation link for the first admin (email delivery arrives in Phase 5): <code>{{ lastInviteUrl() }}</code></p></mat-card-footer> }
      </mat-card>
      <table mat-table [dataSource]="tenants()" class="uf-table">
        <ng-container matColumnDef="name"><th mat-header-cell *matHeaderCellDef>Name</th><td mat-cell *matCellDef="let t"><a [routerLink]="['/t', t.id]">{{ t.name }}</a></td></ng-container>
        <ng-container matColumnDef="slug"><th mat-header-cell *matHeaderCellDef>Slug</th><td mat-cell *matCellDef="let t">{{ t.slug }}</td></ng-container>
        <ng-container matColumnDef="status"><th mat-header-cell *matHeaderCellDef>Status</th><td mat-cell *matCellDef="let t">{{ t.status }}</td></ng-container>
        <ng-container matColumnDef="currency"><th mat-header-cell *matHeaderCellDef>Currency</th><td mat-cell *matCellDef="let t">{{ t.default_currency }}</td></ng-container>
        <tr mat-header-row *matHeaderRowDef="cols"></tr>
        <tr mat-row *matRowDef="let row; columns: cols"></tr>
      </table>
    </div>
  `,
  styles: `.uf-form-row { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }`,
})
export class PlatformTenantsPage {
  private readonly api = inject(UnitformaApi);
  readonly tenants = signal<TenantOut[]>([]);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly lastInviteUrl = signal<string | null>(null);
  readonly cols = ['name', 'slug', 'status', 'currency'];
  slug = '';
  name = '';
  adminEmail = '';

  constructor() {
    void this.load();
  }

  async load(): Promise<void> {
    this.tenants.set(await this.api.listTenants());
  }

  async create(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const t = await this.api.createTenant({ slug: this.slug, name: this.name, default_currency: 'EUR' });
      if (this.adminEmail) {
        const inv = await this.api.inviteTenantAdmin(t.id, this.adminEmail);
        this.lastInviteUrl.set(inv.accept_url ?? null);
      }
      this.slug = this.name = this.adminEmail = '';
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}
