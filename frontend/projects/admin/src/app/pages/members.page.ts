import { SlicePipe } from '@angular/common';
import { Component, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { InvitationOut, MemberOut, ProjectOut, UnitformaApi, problemMessage } from 'api-client';

type Role = 'tenant_admin' | 'project_manager' | 'sales' | 'architectural_reviewer';

@Component({
  selector: 'uf-members-page',
  imports: [SlicePipe, FormsModule, MatCardModule, MatFormFieldModule, MatInputModule, MatSelectModule, MatButtonModule, MatTableModule],
  template: `
    <div class="uf-page">
      @if (error()) { <p class="uf-error">{{ error() }}</p> }
      <mat-card appearance="outlined">
        <mat-card-header><mat-card-title>Invite a colleague</mat-card-title></mat-card-header>
        <mat-card-content class="uf-form-row">
          <mat-form-field appearance="outline"><mat-label>Email</mat-label><input matInput type="email" [(ngModel)]="email" name="email" /></mat-form-field>
          <mat-form-field appearance="outline"><mat-label>Role</mat-label>
            <mat-select [(ngModel)]="role" name="role">
              <mat-option value="tenant_admin">Tenant admin</mat-option>
              <mat-option value="project_manager">Project manager</mat-option>
              <mat-option value="sales">Sales</mat-option>
              <mat-option value="architectural_reviewer">Architectural reviewer</mat-option>
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline"><mat-label>Restrict to projects (optional)</mat-label>
            <mat-select [(ngModel)]="projectIds" name="projectIds" multiple>
              @for (p of projects(); track p.id) { <mat-option [value]="p.id">{{ p.name }}</mat-option> }
            </mat-select>
          </mat-form-field>
          <button mat-flat-button [disabled]="busy()" (click)="invite()">Invite</button>
        </mat-card-content>
        @if (lastInviteUrl()) { <mat-card-footer><p>Invitation link (email delivery arrives in Phase 5): <code>{{ lastInviteUrl() }}</code></p></mat-card-footer> }
      </mat-card>

      <h3>Members</h3>
      <table mat-table [dataSource]="members()" class="uf-table">
        <ng-container matColumnDef="email"><th mat-header-cell *matHeaderCellDef>Email</th><td mat-cell *matCellDef="let m">{{ m.email }}</td></ng-container>
        <ng-container matColumnDef="role"><th mat-header-cell *matHeaderCellDef>Role</th><td mat-cell *matCellDef="let m">
          <mat-select [value]="m.role" (valueChange)="setRole(m, $event)"><mat-option value="tenant_admin">Tenant admin</mat-option><mat-option value="project_manager">Project manager</mat-option><mat-option value="sales">Sales</mat-option><mat-option value="architectural_reviewer">Architectural reviewer</mat-option></mat-select>
        </td></ng-container>
        <ng-container matColumnDef="scope"><th mat-header-cell *matHeaderCellDef>Projects</th><td mat-cell *matCellDef="let m">{{ m.all_projects ? 'all' : m.project_ids.length + ' selected' }}</td></ng-container>
        <ng-container matColumnDef="status"><th mat-header-cell *matHeaderCellDef>Status</th><td mat-cell *matCellDef="let m">
          {{ m.status }}
          <button mat-button (click)="toggle(m)">{{ m.status === 'active' ? 'Suspend' : 'Activate' }}</button>
        </td></ng-container>
        <tr mat-header-row *matHeaderRowDef="memberCols"></tr>
        <tr mat-row *matRowDef="let row; columns: memberCols"></tr>
      </table>

      <h3>Pending invitations</h3>
      <table mat-table [dataSource]="pendingInvitations()" class="uf-table">
        <ng-container matColumnDef="email"><th mat-header-cell *matHeaderCellDef>Email</th><td mat-cell *matCellDef="let i">{{ i.email }}</td></ng-container>
        <ng-container matColumnDef="role"><th mat-header-cell *matHeaderCellDef>Role</th><td mat-cell *matCellDef="let i">{{ i.role }}</td></ng-container>
        <ng-container matColumnDef="expires"><th mat-header-cell *matHeaderCellDef>Expires</th><td mat-cell *matCellDef="let i">{{ i.expires_at | slice: 0 : 10 }}</td></ng-container>
        <ng-container matColumnDef="actions"><th mat-header-cell *matHeaderCellDef></th><td mat-cell *matCellDef="let i"><button mat-button (click)="revoke(i)">Revoke</button></td></ng-container>
        <tr mat-header-row *matHeaderRowDef="inviteCols"></tr>
        <tr mat-row *matRowDef="let row; columns: inviteCols"></tr>
      </table>
    </div>
  `,
  styles: `.uf-form-row { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }`,
})
export class MembersPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly members = signal<MemberOut[]>([]);
  readonly invitations = signal<InvitationOut[]>([]);
  readonly projects = signal<ProjectOut[]>([]);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly lastInviteUrl = signal<string | null>(null);
  readonly memberCols = ['email', 'role', 'scope', 'status'];
  readonly inviteCols = ['email', 'role', 'expires', 'actions'];
  email = '';
  role: Role = 'sales';
  projectIds: string[] = [];

  constructor() {
    toObservable(this.tenantId).subscribe(() => void this.load());
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
    return this.run(async () => {
      const inv = await this.api.createInvitation(this.tenantId(), {
        email: this.email,
        role: this.role,
        all_projects: this.projectIds.length === 0,
        project_ids: this.projectIds,
      });
      this.lastInviteUrl.set(inv.accept_url ?? null);
      this.email = '';
      this.projectIds = [];
    });
  }

  setRole(m: MemberOut, role: Role): Promise<void> {
    return this.run(() => this.api.updateMember(this.tenantId(), m.id, { role }));
  }

  toggle(m: MemberOut): Promise<void> {
    return this.run(() => this.api.updateMember(this.tenantId(), m.id, { status: m.status === 'active' ? 'suspended' : 'active' }));
  }

  revoke(i: InvitationOut): Promise<void> {
    return this.run(() => this.api.revokeInvitation(this.tenantId(), i.id));
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
