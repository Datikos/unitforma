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
export type DocumentOut = Schemas['DocumentOut'];
export type DocumentCreate = Schemas['DocumentCreate'];
export type RevisionOut = Schemas['RevisionOut'];
export type UploadIntentCreate = Schemas['UploadIntentCreate'];
export type UploadIntentOut = Schemas['UploadIntentOut'];
export type SheetOut = Schemas['SheetOut'];
export type Calibration = Schemas['Calibration'];
export type BoundaryCreate = Schemas['BoundaryCreate'];
export type BoundaryOut = Schemas['BoundaryOut'];
export type UnitOut = Schemas['UnitOut'];
export type UnitCreated = Schemas['UnitCreated'];
export type UnitMerge = Schemas['UnitMerge'];
export type UnitSplit = Schemas['UnitSplit'];
export type AreaOut = Schemas['AreaOut'];
export type AreaSet = Schemas['AreaSet'];
export type LineageOut = Schemas['LineageOut'];
export type SuggestionOut = Schemas['SuggestionOut'];
export type ProposalOut = Schemas['ProposalOut'];
export type ProposalItemOut = Schemas['ProposalItemOut'];
export type ProposalDecide = Schemas['ProposalDecide'];
export type FootprintOut = Schemas['FootprintOut'];
export type MassingOut = Schemas['MassingOut'];
export type SiteTransform = Schemas['SiteTransform'];
export type BuildingUpdate = Schemas['BuildingUpdate'];
export type InventoryRow = Schemas['InventoryRow'];
export type SalesChanges = Schemas['SalesChanges'];
export type SalesUpdate = Schemas['SalesUpdate'];
export type BulkUpdate = Schemas['BulkUpdate'];
export type BulkResult = Schemas['BulkResult'];
export type SalesHistoryOut = Schemas['SalesHistoryOut'];
export type SalesSettingsOut = Schemas['SalesSettingsOut'];
export type SalesSettingsIn = Schemas['SalesSettingsIn'];
export type Milestone = Schemas['Milestone'];
export type PaymentPlanIn = Schemas['PaymentPlanIn'];
export type PaymentPlanUpdate = Schemas['PaymentPlanUpdate'];
export type PaymentPlanOut = Schemas['PaymentPlanOut'];
export type PromotionIn = Schemas['PromotionIn'];
export type PromotionUpdate = Schemas['PromotionUpdate'];
export type PromotionOut = Schemas['PromotionOut'];
export type MediaCreate = Schemas['MediaCreate'];
export type MediaUpdate = Schemas['MediaUpdate'];
export type MediaOut = Schemas['MediaOut'];
export type MediaIntentOut = Schemas['MediaIntentOut'];
export type ImportBatchOut = Schemas['ImportBatchOut'];
export type ImportOptions = Schemas['ImportOptions'];
export type Availability = InventoryRow['availability'];
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
  updateBuilding(tenantId: string, buildingId: string, body: BuildingUpdate): Promise<BuildingOut> {
    return this.patch(`${BASE}/admin/tenants/${tenantId}/buildings/${buildingId}`, body);
  }

  // --- geometry (plan §11.3): footprints for placement, generated massing
  listFootprints(tenantId: string, projectId: string): Promise<FootprintOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/footprints`);
  }
  getMassing(tenantId: string, projectId: string): Promise<MassingOut> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/massing`);
  }
  regenerateMassing(tenantId: string, projectId: string): Promise<MassingOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/massing`, undefined);
  }

  // --- documents
  listDocuments(tenantId: string, projectId: string): Promise<DocumentOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/documents`);
  }
  createDocument(tenantId: string, projectId: string, body: DocumentCreate): Promise<DocumentOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/documents`, body);
  }
  createUpload(tenantId: string, documentId: string, body: UploadIntentCreate): Promise<UploadIntentOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/documents/${documentId}/uploads`, body);
  }
  completeUpload(tenantId: string, revisionId: string): Promise<RevisionOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/revisions/${revisionId}/complete`, undefined);
  }
  listRevisions(tenantId: string, documentId: string): Promise<RevisionOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/documents/${documentId}/revisions`);
  }
  listSheets(tenantId: string, revisionId: string): Promise<SheetOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/revisions/${revisionId}/sheets`);
  }
  revisionDownloadUrl(tenantId: string, revisionId: string): Promise<{ url: string }> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/revisions/${revisionId}/download`);
  }
  getSheet(tenantId: string, sheetId: string): Promise<SheetOut> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/sheets/${sheetId}`);
  }
  assignSheetFloor(tenantId: string, sheetId: string, floorId: string | null, version: number): Promise<SheetOut> {
    return this.patch(`${BASE}/admin/tenants/${tenantId}/sheets/${sheetId}/floor`, { floor_id: floorId, version });
  }
  calibrateSheet(tenantId: string, sheetId: string, calibration: Calibration, version: number): Promise<SheetOut> {
    return this.patch(`${BASE}/admin/tenants/${tenantId}/sheets/${sheetId}/calibration`, { calibration, version });
  }

  // --- mapping
  listBoundaries(tenantId: string, sheetId: string): Promise<BoundaryOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/sheets/${sheetId}/boundaries`);
  }
  createBoundary(tenantId: string, sheetId: string, body: BoundaryCreate): Promise<UnitCreated> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/sheets/${sheetId}/boundaries`, body);
  }
  updateBoundary(tenantId: string, boundaryId: string, ring: number[][], version: number): Promise<BoundaryOut> {
    return this.patch(`${BASE}/admin/tenants/${tenantId}/boundaries/${boundaryId}`, { ring, version });
  }
  approveSheet(tenantId: string, sheetId: string): Promise<{ approved_units: number }> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/sheets/${sheetId}/approve`, undefined);
  }
  listUnits(tenantId: string, projectId: string, includeRemoved = false): Promise<UnitOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/units`, { include_removed: String(includeRemoved) });
  }
  getUnit(tenantId: string, unitId: string): Promise<UnitOut> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/units/${unitId}`);
  }
  relabelUnit(tenantId: string, unitId: string, code: string, version: number, reason?: string): Promise<UnitOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/units/${unitId}/relabel`, { code, version, reason: reason ?? null });
  }
  removeUnit(tenantId: string, unitId: string, version: number, note?: string): Promise<UnitOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/units/${unitId}/remove`, { version, note: note ?? null });
  }
  mergeUnits(tenantId: string, projectId: string, body: UnitMerge): Promise<UnitOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/units/merge`, body);
  }
  splitUnit(tenantId: string, unitId: string, body: UnitSplit): Promise<UnitOut[]> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/units/${unitId}/split`, body);
  }
  setArea(tenantId: string, unitId: string, body: AreaSet): Promise<AreaOut> {
    return this.put(`${BASE}/admin/tenants/${tenantId}/units/${unitId}/areas`, body);
  }
  verifyArea(tenantId: string, areaId: string): Promise<AreaOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/areas/${areaId}/verify`, undefined);
  }
  unitHistory(tenantId: string, unitId: string): Promise<{ codes: unknown[]; lineage: LineageOut[] }> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/units/${unitId}/history`);
  }
  projectLineage(tenantId: string, projectId: string): Promise<LineageOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/lineage`);
  }

  // --- suggestions & revision diff proposals (plan §13.2, §13.3)
  suggestBoundaries(tenantId: string, sheetId: string): Promise<SuggestionOut[]> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/sheets/${sheetId}/suggestions`, undefined);
  }
  listProposals(tenantId: string, projectId: string, status?: string): Promise<ProposalOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/proposals`, status ? { status } : undefined);
  }
  getProposal(tenantId: string, proposalId: string): Promise<ProposalOut> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/proposals/${proposalId}`);
  }
  buildProposal(tenantId: string, revisionId: string): Promise<ProposalOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/revisions/${revisionId}/proposals`, undefined);
  }
  decideProposalItem(tenantId: string, proposalId: string, itemId: string, body: ProposalDecide): Promise<ProposalItemOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/proposals/${proposalId}/items/${itemId}`, body);
  }
  acceptProposalItems(tenantId: string, proposalId: string, kinds: string[]): Promise<ProposalOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/proposals/${proposalId}/accept-all`, { kinds });
  }

  // --- sales workspace (plan §6)
  inventory(tenantId: string, projectId: string): Promise<InventoryRow[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/inventory`);
  }
  getUnitSales(tenantId: string, unitId: string): Promise<InventoryRow> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/units/${unitId}/sales`);
  }
  /** Inline edit; a stale `version` rejects with 409 whose body carries `current` (the row). */
  updateUnitSales(tenantId: string, unitId: string, body: SalesUpdate): Promise<InventoryRow> {
    return this.patch(`${BASE}/admin/tenants/${tenantId}/units/${unitId}/sales`, body);
  }
  bulkUpdate(tenantId: string, projectId: string, body: BulkUpdate): Promise<BulkResult> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/inventory/bulk`, body);
  }
  unitSalesHistory(tenantId: string, unitId: string): Promise<SalesHistoryOut> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/units/${unitId}/sales/history`);
  }
  unitPublicPreview(tenantId: string, unitId: string): Promise<Record<string, unknown>> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/units/${unitId}/sales/public-preview`);
  }
  getSalesSettings(tenantId: string, projectId: string): Promise<SalesSettingsOut> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/sales-settings`);
  }
  putSalesSettings(tenantId: string, projectId: string, body: SalesSettingsIn): Promise<SalesSettingsOut> {
    return this.put(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/sales-settings`, body);
  }
  listPaymentPlans(tenantId: string, projectId: string): Promise<PaymentPlanOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/payment-plans`);
  }
  createPaymentPlan(tenantId: string, projectId: string, body: PaymentPlanIn): Promise<PaymentPlanOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/payment-plans`, body);
  }
  updatePaymentPlan(tenantId: string, planId: string, body: PaymentPlanUpdate): Promise<PaymentPlanOut> {
    return this.patch(`${BASE}/admin/tenants/${tenantId}/payment-plans/${planId}`, body);
  }
  listPromotions(tenantId: string, projectId: string): Promise<PromotionOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/promotions`);
  }
  createPromotion(tenantId: string, projectId: string, body: PromotionIn): Promise<PromotionOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/promotions`, body);
  }
  updatePromotion(tenantId: string, promotionId: string, body: PromotionUpdate): Promise<PromotionOut> {
    return this.patch(`${BASE}/admin/tenants/${tenantId}/promotions/${promotionId}`, body);
  }
  listMedia(tenantId: string, unitId: string): Promise<MediaOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/units/${unitId}/media`);
  }
  createMedia(tenantId: string, unitId: string, body: MediaCreate): Promise<MediaIntentOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/units/${unitId}/media`, body);
  }
  completeMedia(tenantId: string, mediaId: string): Promise<MediaOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/media/${mediaId}/complete`, undefined);
  }
  updateMedia(tenantId: string, mediaId: string, body: MediaUpdate): Promise<MediaOut> {
    return this.patch(`${BASE}/admin/tenants/${tenantId}/media/${mediaId}`, body);
  }
  reorderMedia(tenantId: string, unitId: string, ids: string[]): Promise<MediaOut[]> {
    return this.put(`${BASE}/admin/tenants/${tenantId}/units/${unitId}/media/order`, { ids });
  }
  deleteMedia(tenantId: string, mediaId: string): Promise<void> {
    return this.delete(`${BASE}/admin/tenants/${tenantId}/media/${mediaId}`);
  }
  /** Upload a CSV/XLSX file as the raw request body. */
  uploadImport(tenantId: string, projectId: string, file: File): Promise<ImportBatchOut> {
    return firstValueFrom(
      this.http.post<ImportBatchOut>(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/imports`, file, {
        params: toParams({ file_name: file.name }),
        headers: { 'Content-Type': 'application/octet-stream' },
      }),
    );
  }
  listImports(tenantId: string, projectId: string): Promise<ImportBatchOut[]> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/imports`);
  }
  getImport(tenantId: string, batchId: string): Promise<ImportBatchOut> {
    return this.get(`${BASE}/admin/tenants/${tenantId}/imports/${batchId}`);
  }
  dryRunImport(tenantId: string, batchId: string, mapping: Record<string, string>, options: ImportOptions): Promise<ImportBatchOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/imports/${batchId}/dry-run`, { mapping, options });
  }
  applyImport(tenantId: string, batchId: string, skipInvalidRows: boolean): Promise<ImportBatchOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/imports/${batchId}/apply`, { skip_invalid_rows: skipInvalidRows });
  }
  discardImport(tenantId: string, batchId: string): Promise<ImportBatchOut> {
    return this.post(`${BASE}/admin/tenants/${tenantId}/imports/${batchId}/discard`, undefined);
  }
  /** Download the inventory as CSV or XLSX (same columns as the importer reads). */
  async downloadInventory(tenantId: string, projectId: string, format: 'csv' | 'xlsx', columns: 'internal' | 'public'): Promise<void> {
    const res = await firstValueFrom(
      this.http.get(`${BASE}/admin/tenants/${tenantId}/projects/${projectId}/inventory/export`, {
        params: toParams({ format, columns }),
        responseType: 'blob',
        observe: 'response',
      }),
    );
    const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? `inventory.${format}`;
    const url = URL.createObjectURL(res.body!);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  /** Upload a file to a presigned PUT URL (S3 or the local dev backend), reporting progress 0..1. */
  uploadToPresignedUrl(url: string, file: File, contentType: string, onProgress?: (p: number) => void): Promise<void> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('PUT', url, true);
      xhr.setRequestHeader('Content-Type', contentType);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
      };
      xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`upload failed (${xhr.status})`)));
      xhr.onerror = () => reject(new Error('upload failed (network)'));
      xhr.send(file);
    });
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
