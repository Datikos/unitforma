import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import type { components } from '../generated/openapi';

export type Schemas = components['schemas'];
export type MeOut = Schemas['MeOut'];
export type MembershipSummary = Schemas['MembershipSummary'];
export type TenantOut = Schemas['TenantOut'];
export type TenantCreate = Schemas['TenantCreate'];
export type TenantUpdate = Schemas['TenantUpdate'];
export type MemberOut = Schemas['MemberOut'];
export type MemberUpdate = Schemas['MemberUpdate'];
export type InvitationCreate = Schemas['InvitationCreate'];
export type InvitationOut = Schemas['InvitationOut'];
export type ProjectOut = Schemas['ProjectOut'];
export type ProjectCreate = Schemas['ProjectCreate'];
export type ProjectUpdate = Schemas['ProjectUpdate'];
export type BuildingOut = Schemas['BuildingOut'];
export type BuildingCreate = Schemas['BuildingCreate'];
export type FloorIn = Schemas['FloorIn'];
export type FloorOut = Schemas['FloorOut'];
export type SiteFeatureOut = Schemas['SiteFeatureOut'];
export type SiteFeatureCreate = Schemas['SiteFeatureCreate'];
export type AuditOut = Schemas['AuditOut'];
export interface Page<T> {
  items: T[];
  total: number;
}

/** RFC 9457 problem details as returned by the backend for every error. */
export interface Problem {
  type: string;
  title: string;
  status: number;
  detail?: string;
  errors?: unknown[];
}

const BASE = '/api/v1';

/**
 * Typed client for the Unitforma admin and platform APIs.
 * Types come from the generated OpenAPI document (`npm run api:generate`).
 */
@Injectable({ providedIn: 'root' })
export class UnitformaApi {
  private readonly http = inject(HttpClient);

  // --- identity
  me(): Promise<MeOut> {
    return this.get(`${BASE}/admin/me`);
  }
  acceptInvitation(token: string): Promise<MembershipSummary> {
    return this.post(`${BASE}/admin/invitations/accept`, { token });
  }

  // --- platform
  listTenants(): Promise<TenantOut[]> {
    return this.get(`${BASE}/platform/tenants`);
  }
  createTenant(body: TenantCreate): Promise<TenantOut> {
    return this.post(`${BASE}/platform/tenants`, body);
  }
  inviteTenantAdmin(tenantId: string, email: string): Promise<InvitationOut> {
    return this.post(`${BASE}/platform/tenants/${tenantId}/invitations`, undefined, { email });
  }

  // --- tenant
  getTenant(tenantId: string): Promise<TenantOut> {
    return this.get(`${BASE}/admin/tenants/${tenantId}`);
  }
  updateTenant(tenantId: string, body: TenantUpdate): Promise<TenantOut> {
    return this.patch(`${BASE}/admin/tenants/${tenantId}`, body);
  }
  listMembers(tenantId: string): Promise<MemberOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/members`);
  }
  updateMember(tenantId: string, membershipId: string, body: MemberUpdate): Promise<MemberOut> {
    return this.patch(`${BASE}/admin/tenants/${tenantId}/members/${membershipId}`, body);
  }
  listInvitations(tenantId: string): Promise<InvitationOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/invitations`);
  }
  createInvitation(tenantId: string, body: InvitationCreate): Promise<InvitationOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/invitations`, body);
  }
  revokeInvitation(tenantId: string, invitationId: string): Promise<void> {
    return this.delete(`${BASE}/admin/tenants/${tenantId}/invitations/${invitationId}`);
  }
  listAudit(tenantId: string, limit = 50, offset = 0): Promise<Page<AuditOut>> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/audit`, { limit, offset });
  }

  // --- projects
  listProjects(tenantId: string): Promise<ProjectOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects`);
  }
  createProject(tenantId: string, body: ProjectCreate): Promise<ProjectOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/projects`, body);
  }
  getProject(tenantId: string, projectId: string): Promise<ProjectOut> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}`);
  }
  updateProject(tenantId: string, projectId: string, body: ProjectUpdate): Promise<ProjectOut> {
    return this.patch(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}`, body);
  }
  listBuildings(tenantId: string, projectId: string): Promise<BuildingOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/buildings`);
  }
  createBuilding(tenantId: string, projectId: string, body: BuildingCreate): Promise<BuildingOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/buildings`, body);
  }
  setFloors(tenantId: string, buildingId: string, floors: FloorIn[]): Promise<FloorOut[]> {
    return this.put(`${BASE}/admin/tenants/${tenantId}/buildings/${buildingId}/floors`, { floors });
  }
  listSiteFeatures(tenantId: string, projectId: string): Promise<SiteFeatureOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/site-features`);
  }
  createSiteFeature(tenantId: string, projectId: string, body: SiteFeatureCreate): Promise<SiteFeatureOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/site-features`, body);
  }

  // --- transport
  private get<T>(url: string, params?: Record<string, string | number>): Promise<T> {
    return firstValueFrom(this.http.get<T>(url, { params: toParams(params) }));
  }
  private post<T>(url: string, body: unknown, params?: Record<string, string | number>): Promise<T> {
    return firstValueFrom(this.http.post<T>(url, body ?? null, { params: toParams(params) }));
  }
  private put<T>(url: string, body: unknown): Promise<T> {
    return firstValueFrom(this.http.put<T>(url, body));
  }
  private patch<T>(url: string, body: unknown): Promise<T> {
    return firstValueFrom(this.http.patch<T>(url, body));
  }
  private delete<T>(url: string): Promise<T> {
    return firstValueFrom(this.http.delete<T>(url));
  }
}

function toParams(params?: Record<string, string | number>): HttpParams | undefined {
  if (!params) return undefined;
  let p = new HttpParams();
  for (const [k, v] of Object.entries(params)) p = p.set(k, String(v));
  return p;
}

/** Extract a human-readable message from an HttpErrorResponse carrying problem+json. */
export function problemMessage(err: unknown): string {
  const e = err as { error?: Problem; message?: string; status?: number };
  const p = e?.error;
  if (p && typeof p === 'object' && 'title' in p) return p.detail ? `${p.title}: ${p.detail}` : p.title;
  if (e?.status === 0) return 'Network error';
  return e?.message ?? 'Unexpected error';
}
