import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

/** Shapes of the public portal API (backend `publishing.snapshot`, plan §9.3). */
export type Availability = 'available' | 'reserved' | 'sold' | 'withdrawn';
export type Point = [number, number];

export interface Money {
  amount: string;
  currency: string;
}

export interface Branding {
  primary_color?: string;
  accent_color?: string;
  display_name?: string;
  tagline?: string;
  contact_email?: string;
  contact_phone?: string;
  website?: string;
  legal_text?: string;
}

export interface Stats {
  units: number;
  available: number;
  price_from: Money | null;
  area_min: string | null;
  area_max: string | null;
  rooms: number[];
  unit_types: string[];
}

export interface ProjectCard {
  slug: string;
  name: string;
  hero_text?: string;
  construction_stage?: string;
  address?: Record<string, string | number>;
  stats: Stats;
  /** First gallery image, when the developer published renders (ADR-0016). */
  cover?: string | null;
}

/** A page of a public render document (ADR-0016 Decision 1). */
export interface GalleryItem extends PlanRef {
  caption: string;
  document: string;
  page: number;
}

/** A public site feature: ring on the site plan (normalised) and in site-frame metres. */
export interface SiteFeatureDoc {
  kind: string;
  name: string;
  ring: Point[];
  ring_m?: Point[];
}

export interface SiteOut {
  tenant: { name: string; slug: string };
  branding: Branding;
  mode: 'tenant' | 'project';
  projects: ProjectCard[];
  status: 'live' | 'coming_soon';
  /** False: the project page shows the address and a link instead of the OSM iframe (ADR-0016 E4). */
  map_embed?: boolean;
}

export interface PlanRef {
  asset: string;
  url: string;
  width: number;
  height: number;
}

export interface FloorUnit {
  id: string;
  code: string;
  unit_type: string;
  availability: Availability;
  /** Staircase; public like the floor (ADR-0014 Decision 2). */
  entrance?: string | null;
  ring: Point[] | null;
}

export type ConstructionStatus = 'planned' | 'under_construction' | 'completed';

/** One clickable floor band on the building's elevation drawing (ADR-0014 Decision 1). */
export interface ElevationBand {
  level: number;
  /** False when the floor has no published unit: drawn, not clickable. */
  published: boolean;
  ring: Point[];
}

export interface ElevationDoc {
  plan: PlanRef;
  bands: ElevationBand[];
}

export interface FloorDoc {
  level: number;
  name: string;
  plan: PlanRef | null;
  units: FloorUnit[];
}

export interface BuildingDoc {
  code: string;
  name: string | null;
  kind: string;
  floors: FloorDoc[];
  /** Distinct entrances of the listed units (ADR-0014 Decision 2). */
  entrances?: string[];
  construction_status?: ConstructionStatus | null;
  completion?: string | null;
  /** The building's own terms, else the project default (ADR-0014 Decision 3). */
  terms?: string | null;
  /** The architect's IFC model of this building when one was ingested and confirmed (ADR-0006 Phase C). */
  model?: {
    url: string;
    bytes: number;
    kind: string;
    disclaimer: string;
    built_at: string | null;
  } | null;
  /** The elevation floor picker when the reviewer chose a sheet and its markers matched (ADR-0014). */
  elevation?: ElevationDoc | null;
}

export interface AreaDefinition {
  key: string;
  label: string;
  description?: string | null;
}

export interface PaymentPlan {
  name: string;
  description?: string | null;
  schedule: { label: string; percent: string; due?: string | null }[];
}

export interface Promotion {
  name: string;
  kind: string;
  value?: string | null;
  terms?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
}

export interface ProjectDoc {
  publication: { id: string; version_no: number; status: string; built_at: string };
  tenant: { name: string; slug: string };
  branding: Branding;
  project: {
    slug: string;
    name: string;
    description?: string | null;
    /** Text lines plus `lat` / `lng` when the developer set the map position. */
    address: Record<string, string | number>;
    currency: string;
    area_definitions: AreaDefinition[];
    price_area_type: string;
    hero_text?: string;
    construction_stage?: string;
    completion?: string;
    /** Printed next to every price (ADR-0014 Decision 4). */
    price_note?: string;
    /** Default terms; each building carries its effective terms already. */
    terms?: string;
  };
  stats: Stats;
  site: {
    plan: PlanRef | null;
    buildings: {
      code: string;
      name: string | null;
      floors: number;
      height_m: number;
      construction_status?: ConstructionStatus | null;
      ring: Point[] | null;
    }[];
    features?: SiteFeatureDoc[];
  } | null;
  gallery?: GalleryItem[];
  buildings: BuildingDoc[];
  massing: { url: string; units: number; bytes: number; disclaimer: string } | null;
  payment_plans: PaymentPlan[];
  promotions: Promotion[];
  preview: boolean;
}

export interface UnitMedia {
  kind: string;
  alt_text?: string | null;
  is_ai_generated: boolean;
  ai_disclosure_text?: string | null;
  url: string;
  mime: string;
  /** Code of the unit whose media this is, when shown here because both share a layout. */
  shared_from?: string;
}

export interface UnitDoc {
  unit_id: string;
  code: string;
  building_code: string;
  floor_level: number;
  floor_name: string;
  unit_type: string;
  availability: Availability;
  entrance?: string;
  indicative: boolean;
  /** Plan type shared by several units; their renders are shared too (ADR-0016). */
  layout?: string;
  /** Wall finish the developer stated: a RAL code or a hex colour (ADR-0017 E5). */
  wall_colour?: string;
  listed: boolean;
  price:
    (Money & { per_m2?: string; per_m2_area_type?: string; per_m2_area_verified?: boolean }) | null;
  areas?: Record<string, string>;
  rooms?: {
    rooms: number | null;
    bedrooms: number | null;
    bathrooms: number | null;
    orientation: string | null;
  };
  description?: string;
  payment_plan?: PaymentPlan;
  promotions?: Promotion[];
  media?: UnitMedia[];
  plan?: PlanRef & { ring: Point[] | null };
}

export interface UnitFilters {
  availability?: Availability[];
  unit_type?: string[];
  building?: string[];
  floor?: number[];
  /** Applied by the API only together with `building` (ADR-0014 Decision 2). */
  entrance?: string[];
  rooms?: number[];
  min_price?: number | null;
  max_price?: number | null;
  min_area?: number | null;
  max_area?: number | null;
  sort?: 'code' | 'price_asc' | 'price_desc' | 'area_asc' | 'area_desc';
}

export interface Problem {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
}

const BASE = '/api/v1/portal';
const PREVIEW_KEY = 'uf:preview';

/** Anonymous portal API. The host decides the tenant; a `?preview=` token is remembered for the tab. */
@Injectable({ providedIn: 'root' })
export class PortalApi {
  private readonly http = inject(HttpClient);
  readonly previewToken = signal<string | null>(readPreview());

  site(): Promise<SiteOut> {
    return this.get(`${BASE}/site`);
  }
  project(slug: string): Promise<ProjectDoc> {
    return this.get(`${BASE}/projects/${encodeURIComponent(slug)}`);
  }
  units(slug: string, f: UnitFilters): Promise<{ total: number; items: UnitDoc[] }> {
    let p = new HttpParams();
    for (const [k, v] of Object.entries(f)) {
      if (v === null || v === undefined || v === '') continue;
      if (Array.isArray(v)) v.forEach((x) => (p = p.append(k, String(x))));
      else p = p.set(k, String(v));
    }
    return this.get(`${BASE}/projects/${encodeURIComponent(slug)}/units`, p);
  }
  unit(slug: string, code: string): Promise<UnitDoc> {
    return this.get(
      `${BASE}/projects/${encodeURIComponent(slug)}/units/${encodeURIComponent(code)}`,
    );
  }

  /** Asset URLs come from the snapshot; in preview mode the token must travel with them. */
  asset(url: string | null | undefined): string | null {
    if (!url) return null;
    const t = this.previewToken();
    return t ? `${url}${url.includes('?') ? '&' : '?'}preview=${encodeURIComponent(t)}` : url;
  }

  endPreview(): void {
    this.previewToken.set(null);
    try {
      sessionStorage.removeItem(PREVIEW_KEY);
    } catch {
      /* storage unavailable */
    }
  }

  private get<T>(url: string, params?: HttpParams): Promise<T> {
    const t = this.previewToken();
    const headers = t ? new HttpHeaders({ 'X-Unitforma-Preview': t }) : undefined;
    return firstValueFrom(this.http.get<T>(url, { params, headers }));
  }
}

function readPreview(): string | null {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('preview');
    if (fromUrl) {
      sessionStorage.setItem(PREVIEW_KEY, fromUrl);
      return fromUrl;
    }
    return sessionStorage.getItem(PREVIEW_KEY);
  } catch {
    return null;
  }
}

export function problemOf(e: unknown): Problem {
  const err = e as { error?: Problem; status?: number };
  return { ...(err?.error && typeof err.error === 'object' ? err.error : {}), status: err?.status };
}
