import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { TenantOut, UnitformaApi, problemMessage } from 'api-client';
import {
  EmptyStateComponent,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
} from 'ui';
import { ToastService } from '../ui/toast.service';

/** Platform console: create developer workspaces and invite their first administrator (plan J1). */
@Component({
  selector: 'uf-platform-tenants-page',
  imports: [
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    RouterLink,
    NgIcon,
    PageHeaderComponent,
    SectionCardComponent,
    StatusChipComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header
        title="Tenants"
        icon="lucideLandmark"
        kicker="Platform"
        [facts]="[
          { label: 'Tenants', value: tenants().length },
          { domain: 'tenant', status: 'active', value: activeCount() + ' active' },
        ]"
      />
      <uf-section-card
        title="Create a tenant"
        icon="lucidePlus"
        summary="slug becomes {slug}.unitforma.com"
        storageKey="platform-create"
        [open]="tenants().length === 0"
      >
        <div class="uf-form-row">
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>Slug (subdomain)</mat-label
            ><input matInput [(ngModel)]="slug" name="slug" placeholder="acme-homes"
          /></mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>Name</mat-label
            ><input matInput [(ngModel)]="name" name="name" placeholder="Acme Homes LLC"
          /></mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>First admin email</mat-label
            ><input matInput type="email" [(ngModel)]="adminEmail" name="adminEmail"
          /></mat-form-field>
          <button
            mat-flat-button
            [disabled]="busy() || !slug.trim() || !name.trim()"
            (click)="create()"
          >
            Create
          </button>
        </div>
        <p class="uf-hint">
          The workspace starts with EUR as its default currency. The first admin receives an
          invitation link; until e-mail delivery exists, copy and send it yourself.
        </p>
        @if (error(); as e) {
          <div class="uf-alert uf-alert--bad" role="alert">
            <ng-icon name="lucideCircleX" />{{ e }}
          </div>
        }
        @if (lastInviteUrl(); as url) {
          <div class="uf-alert uf-alert--good">
            <ng-icon name="lucideLink" />
            <div>
              Invitation link for the first admin:<br /><code class="uf-mono">{{ url }}</code>
            </div>
          </div>
        }
      </uf-section-card>

      @if (tenants().length) {
        <div class="uf-filterbar">
          <mat-form-field appearance="outline" subscriptSizing="dynamic" class="search"
            ><ng-icon matPrefix name="lucideSearch" /><input
              matInput
              [ngModel]="query()"
              (ngModelChange)="query.set($event)"
              placeholder="Search name or slug"
              aria-label="Search tenants"
          /></mat-form-field>
          <span class="uf-count">{{ shown().length }} of {{ tenants().length }}</span>
        </div>
        <div class="uf-card" style="padding: 0">
          <table class="uf-plain">
            <thead>
              <tr>
                <th>Name</th>
                <th>Portal</th>
                <th>Status</th>
                <th>Currency</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (t of shown(); track t.id) {
                <tr>
                  <td>
                    <a class="uf-link" [routerLink]="['/t', t.id]"
                      ><strong>{{ t.name }}</strong></a
                    >
                  </td>
                  <td class="uf-muted">{{ t.slug }}.unitforma.com</td>
                  <td><uf-status-chip domain="tenant" [value]="t.status" /></td>
                  <td>{{ t.default_currency }}</td>
                  <td class="actions">
                    <a mat-button [routerLink]="['/t', t.id]"
                      >Open <ng-icon name="lucideArrowRight"
                    /></a>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else if (loaded()) {
        <uf-empty-state
          icon="lucideLandmark"
          title="No tenants yet"
          text="Create the first developer workspace above."
        />
      }
    </div>
  `,
  styles: `
    .search {
      min-width: 260px;
    }
    .search ng-icon {
      margin: 0 0.25rem 0 0.5rem;
      color: var(--uf-muted);
    }
    .actions {
      text-align: right;
    }
    a ng-icon {
      vertical-align: -0.15em;
    }
  `,
})
export class PlatformTenantsPage {
  private readonly api = inject(UnitformaApi);
  private readonly toast = inject(ToastService);
  readonly tenants = signal<TenantOut[]>([]);
  readonly loaded = signal(false);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly lastInviteUrl = signal<string | null>(null);
  readonly query = signal('');
  readonly shown = computed(() => {
    const q = this.query().trim().toLowerCase();
    return q
      ? this.tenants().filter((t) => `${t.name} ${t.slug}`.toLowerCase().includes(q))
      : this.tenants();
  });
  readonly activeCount = computed(() => this.tenants().filter((t) => t.status === 'active').length);
  slug = '';
  name = '';
  adminEmail = '';

  constructor() {
    void this.load();
  }

  async load(): Promise<void> {
    try {
      this.tenants.set(await this.api.listTenants());
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.loaded.set(true);
    }
  }

  async create(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const t = await this.api.createTenant({
        slug: this.slug.trim(),
        name: this.name.trim(),
        default_currency: 'EUR',
      });
      if (this.adminEmail) {
        const inv = await this.api.inviteTenantAdmin(t.id, this.adminEmail);
        this.lastInviteUrl.set(inv.accept_url ?? null);
      }
      this.toast.ok(`Tenant ${t.name} created`);
      this.slug = this.name = this.adminEmail = '';
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}
