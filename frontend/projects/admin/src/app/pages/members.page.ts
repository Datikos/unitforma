import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { InvitationOut, MemberOut, ProjectOut, UnitformaApi, problemMessage } from 'api-client';
import {
  EmptyStateComponent,
  HeaderFact,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
  dayOf,
  labelOf,
} from 'ui';
import { DialogsService } from '../ui/dialogs.service';
import { ToastService } from '../ui/toast.service';

type Role = 'tenant_admin' | 'project_manager' | 'sales' | 'architectural_reviewer';
const ROLES: { value: Role; label: string; does: string }[] = [
  {
    value: 'tenant_admin',
    label: 'Tenant admin',
    does: 'everything, including members and branding',
  },
  {
    value: 'project_manager',
    label: 'Project manager',
    does: 'structure, documents, placement, publishing',
  },
  { value: 'sales', label: 'Sales', does: 'inventory, prices, plans and promotions' },
  {
    value: 'architectural_reviewer',
    label: 'Architectural reviewer',
    does: 'sheet mapping and revision diffs',
  },
];

/** Workspace members and invitations (plan §2.2 roles). */
@Component({
  selector: 'uf-members-page',
  imports: [
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    NgIcon,
    PageHeaderComponent,
    SectionCardComponent,
    StatusChipComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header title="Members" icon="lucideUsers" [facts]="facts()" />
      @if (error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }

      <uf-section-card
        title="Invite a colleague"
        icon="lucideUserPlus"
        summary="e-mail, role, optional project restriction"
        storageKey="members-invite"
        [open]="members().length <= 1"
      >
        <div class="uf-form-row">
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>Email</mat-label
            ><input matInput type="email" [(ngModel)]="email" name="email" (keyup.enter)="invite()"
          /></mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>Role</mat-label>
            <mat-select [(ngModel)]="role" name="role">
              @for (r of roles; track r.value) {
                <mat-option [value]="r.value">{{ r.label }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>Restrict to projects (optional)</mat-label>
            <mat-select [(ngModel)]="projectIds" name="projectIds" multiple>
              @for (p of projects(); track p.id) {
                <mat-option [value]="p.id">{{ p.name }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <button mat-flat-button [disabled]="busy() || !email.trim()" (click)="invite()">
            <ng-icon name="lucideMail" /> Invite
          </button>
        </div>
        <p class="uf-hint">
          {{ roleHelp() }}. The invitation is tied to the e-mail address; without a project
          restriction the member sees every project.
        </p>
        @if (lastInviteUrl(); as url) {
          <div class="uf-alert uf-alert--good">
            <ng-icon name="lucideLink" />
            <div>
              Invitation link (e-mail delivery arrives in Phase 5): copy and send it yourself.<br /><code
                class="uf-mono"
                >{{ url }}</code
              >
            </div>
          </div>
        }
      </uf-section-card>

      <uf-section-card
        title="Members"
        icon="lucideUsers"
        [count]="members().length"
        [summary]="activeCount() + ' active'"
        [flush]="true"
        [collapsible]="false"
      >
        @if (members().length > 10) {
          <div actions>
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="search"
              ><ng-icon matPrefix name="lucideSearch" /><input
                matInput
                [ngModel]="query()"
                (ngModelChange)="query.set($event)"
                placeholder="Search e-mail"
                aria-label="Search members"
            /></mat-form-field>
          </div>
        }
        @if (shown().length) {
          <table class="uf-plain">
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Projects</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (m of shown(); track m.id) {
                <tr>
                  <td>
                    <strong>{{ m.email }}</strong>
                  </td>
                  <td>
                    <mat-select
                      class="role"
                      [value]="m.role"
                      (valueChange)="setRole(m, $event)"
                      aria-label="Role"
                    >
                      @for (r of roles; track r.value) {
                        <mat-option [value]="r.value">{{ r.label }}</mat-option>
                      }
                    </mat-select>
                  </td>
                  <td>
                    {{ m.all_projects ? 'all projects' : m.project_ids.length + ' selected' }}
                  </td>
                  <td><uf-status-chip domain="member" [value]="m.status" /></td>
                  <td class="actions">
                    <button mat-button (click)="toggle(m)">
                      <ng-icon [name]="m.status === 'active' ? 'lucideBan' : 'lucideCircleCheck'" />
                      {{ m.status === 'active' ? 'Suspend' : 'Activate' }}
                    </button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        } @else {
          <uf-empty-state
            icon="lucideUsers"
            title="No members yet"
            text="Invite colleagues above; you are the only member until they accept."
            [compact]="true"
          />
        }
      </uf-section-card>

      <uf-section-card
        title="Pending invitations"
        icon="lucideMail"
        [count]="pendingInvitations().length"
        [summary]="pendingInvitations().length ? 'waiting to be accepted' : 'none'"
        [flush]="true"
        storageKey="members-invitations"
        [open]="pendingInvitations().length > 0"
      >
        @if (pendingInvitations().length) {
          <table class="uf-plain">
            <thead>
              <tr>
                <th>Email</th>
                <th>Role</th>
                <th>Expires</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (i of pendingInvitations(); track i.id) {
                <tr>
                  <td>{{ i.email }}</td>
                  <td><uf-status-chip domain="role" [value]="i.role" /></td>
                  <td>{{ day(i.expires_at) }}</td>
                  <td class="actions">
                    <button mat-button (click)="revoke(i)">
                      <ng-icon name="lucideX" /> Revoke
                    </button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        } @else {
          <p class="uf-muted uf-small pad">No open invitations.</p>
        }
      </uf-section-card>
    </div>
  `,
  styles: `
    .role {
      min-width: 12rem;
    }
    .search {
      min-width: 220px;
    }
    .search ng-icon {
      margin: 0 0.25rem 0 0.5rem;
      color: var(--uf-muted);
    }
    .actions {
      text-align: right;
      white-space: nowrap;
    }
    .pad {
      padding: 0.75rem 1rem;
      margin: 0;
    }
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class MembersPage {
  private readonly api = inject(UnitformaApi);
  private readonly dialogs = inject(DialogsService);
  private readonly toast = inject(ToastService);
  readonly tenantId = input.required<string>();
  readonly members = signal<MemberOut[]>([]);
  readonly invitations = signal<InvitationOut[]>([]);
  readonly projects = signal<ProjectOut[]>([]);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly lastInviteUrl = signal<string | null>(null);
  readonly query = signal('');
  readonly roles = ROLES;
  readonly activeCount = computed(() => this.members().filter((m) => m.status === 'active').length);
  readonly shown = computed(() => {
    const q = this.query().trim().toLowerCase();
    return q ? this.members().filter((m) => m.email.toLowerCase().includes(q)) : this.members();
  });
  readonly facts = computed<HeaderFact[]>(() => [
    { label: 'Members', value: this.members().length },
    { domain: 'member', status: 'active', value: `${this.activeCount()} active` },
    { domain: 'member', status: 'invited', value: `${this.pendingInvitations().length} invited` },
  ]);
  email = '';
  role: Role = 'sales';
  projectIds: string[] = [];
  day = dayOf;

  constructor() {
    toObservable(this.tenantId).subscribe(() => void this.load());
  }

  roleHelp(): string {
    const r = ROLES.find((x) => x.value === this.role);
    return r ? `${r.label}: ${r.does}` : '';
  }

  pendingInvitations(): InvitationOut[] {
    return this.invitations().filter((i) => !i.accepted);
  }

  async load(): Promise<void> {
    try {
      const [m, i, p] = await Promise.all([
        this.api.listMembers(this.tenantId()),
        this.api.listInvitations(this.tenantId()),
        this.api.listProjects(this.tenantId()),
      ]);
      this.members.set(m);
      this.invitations.set(i);
      this.projects.set(p);
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  invite(): Promise<void> {
    if (!this.email.trim()) return Promise.resolve();
    return this.run(async () => {
      const inv = await this.api.createInvitation(this.tenantId(), {
        email: this.email.trim(),
        role: this.role,
        all_projects: this.projectIds.length === 0,
        project_ids: this.projectIds,
      });
      this.lastInviteUrl.set(inv.accept_url ?? null);
      this.toast.ok(`Invitation created for ${this.email.trim()}`);
      this.email = '';
      this.projectIds = [];
    });
  }

  setRole(m: MemberOut, role: Role): Promise<void> {
    return this.run(async () => {
      await this.api.updateMember(this.tenantId(), m.id, { role });
      this.toast.ok(`${m.email} is now ${labelOf('role', role)}`);
    });
  }

  async toggle(m: MemberOut): Promise<void> {
    const suspend = m.status === 'active';
    if (suspend) {
      const ok = await this.dialogs.confirm({
        title: `Suspend ${m.email}?`,
        message: 'The member keeps their record but cannot sign in to this workspace.',
        consequence: 'Activate reverses it at any time.',
        confirmLabel: 'Suspend',
        tone: 'bad',
      });
      if (!ok) return;
    }
    return this.run(async () => {
      await this.api.updateMember(this.tenantId(), m.id, {
        status: suspend ? 'suspended' : 'active',
      });
      this.toast.ok(`${m.email} ${suspend ? 'suspended' : 'activated'}`);
    });
  }

  async revoke(i: InvitationOut): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: `Revoke the invitation for ${i.email}?`,
      message: 'The link stops working. You can invite the address again later.',
      confirmLabel: 'Revoke',
      tone: 'bad',
    });
    if (!ok) return;
    return this.run(async () => {
      await this.api.revokeInvitation(this.tenantId(), i.id);
      this.toast.ok('Invitation revoked');
    });
  }

  private async run(fn: () => Promise<unknown>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await fn();
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}
