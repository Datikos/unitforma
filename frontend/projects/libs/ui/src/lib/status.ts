import { iconSvg } from './icons';

/** The six tones every status in the product maps to (ADR-0009 Decision 3). */
export type Tone = 'good' | 'warning' | 'bad' | 'info' | 'neutral' | 'pending';

export interface StatusView {
  tone: Tone;
  label: string;
  /** Icon name registered in `UF_ICONS`. */
  icon: string;
}

type Table = Record<string, StatusView>;

const v = (tone: Tone, label: string, icon: string): StatusView => ({ tone, label, icon });

/**
 * Status vocabulary per domain. Values come from the backend check constraints
 * (`backend/migrations/versions`) and `api/schemas.py` literals; the same word always has the
 * same colour and icon on every page and in the grid.
 */
export const STATUS_TABLES = {
  availability: {
    available: v('good', 'Available', 'lucideCircleCheck'),
    reserved: v('warning', 'Reserved', 'lucideClock'),
    sold: v('bad', 'Sold', 'lucideCircleX'),
    withdrawn: v('neutral', 'Not for sale', 'lucideCircleSlash'),
  },
  'unit.lifecycle': {
    draft: v('pending', 'Draft', 'lucideCircleDashed'),
    active: v('good', 'Active', 'lucideCircleDot'),
    removed: v('neutral', 'Removed', 'lucideCircleX'),
  },
  'unit.verification': {
    unverified: v('warning', 'Unverified', 'lucideCircleAlert'),
    pending: v('warning', 'Pending', 'lucideClock'),
    in_review: v('pending', 'In review', 'lucideEye'),
    verified: v('good', 'Verified', 'lucideShieldCheck'),
  },
  'unit.publication': {
    unpublished: v('neutral', 'Not published', 'lucideEyeOff'),
    published: v('good', 'Public', 'lucideGlobe'),
    hidden: v('info', 'Link only', 'lucideLink'),
  },
  'document.processing': {
    pending: v('neutral', 'Waiting', 'lucideClock'),
    queued: v('pending', 'Queued', 'lucideClock'),
    processing: v('pending', 'Processing', 'lucideLoaderCircle'),
    running: v('pending', 'Processing', 'lucideLoaderCircle'),
    done: v('good', 'Processed', 'lucideCircleCheck'),
    partial: v('warning', 'Partly processed', 'lucideTriangleAlert'),
    skipped: v('neutral', 'Not processed', 'lucideCircleSlash'),
    failed: v('bad', 'Failed', 'lucideCircleX'),
  },
  'document.kind_source': {
    manual: v('good', 'Set by you', 'lucideCheck'),
    filename: v('info', 'Guessed from the name', 'lucideSparkles'),
    content: v('info', 'Guessed from the content', 'lucideSparkles'),
    pending: v('warning', 'Needs a kind', 'lucideCircleHelp'),
  },
  'document.kind': {
    site_plan: v('neutral', 'Site plan', 'lucideMap'),
    floor_plan: v('neutral', 'Floor plans', 'lucideLayers'),
    section: v('neutral', 'Sections', 'lucideSplit'),
    elevation: v('neutral', 'Elevations', 'lucideBuilding'),
    render: v('neutral', 'Renders', 'lucideImage'),
    schedule: v('neutral', 'Area schedule', 'lucideTable'),
    model_ifc: v('neutral', 'IFC model', 'lucideBox'),
    model_glb: v('neutral', 'GLB model', 'lucideBox'),
    texture: v('neutral', 'Texture', 'lucideFileImage'),
    permit: v('neutral', 'Permit document', 'lucideScrollText'),
    other: v('neutral', 'Other', 'lucideFileText'),
    unclassified: v('warning', 'Uncategorized', 'lucideCircleHelp'),
  },
  'sheet.assignment': {
    unassigned: v('warning', 'Unassigned', 'lucideCircleHelp'),
    suggested: v('pending', 'Suggested', 'lucideSparkles'),
    confirmed: v('good', 'Confirmed', 'lucideCircleCheck'),
    excluded: v('neutral', 'Excluded', 'lucideBan'),
  },
  'sheet.calibration': {
    none: v('warning', 'Not calibrated', 'lucideRuler'),
    calibrated: v('good', 'Calibrated', 'lucideRuler'),
    inherited: v('info', 'Scale inherited', 'lucideRuler'),
  },
  'sheet.floor': {
    suggested: v('pending', 'Suggested', 'lucideSparkles'),
    confirmed: v('good', 'Confirmed', 'lucideCircleCheck'),
  },
  'revision.status': {
    draft: v('pending', 'Draft', 'lucideCircleDashed'),
    approved: v('good', 'Approved', 'lucideCircleCheck'),
    superseded: v('neutral', 'Superseded', 'lucideHistory'),
  },
  'proposal.status': {
    open: v('warning', 'Open', 'lucideCircleDot'),
    resolved: v('good', 'Resolved', 'lucideCircleCheck'),
    dismissed: v('neutral', 'Dismissed', 'lucideBan'),
  },
  'proposal.kind': {
    matched: v('good', 'Matched', 'lucideCheck'),
    relabelled: v('info', 'Relabelled', 'lucideTag'),
    split: v('warning', 'Split', 'lucideSplit'),
    merged: v('warning', 'Merged', 'lucideMerge'),
    new: v('info', 'New', 'lucidePlus'),
    missing: v('bad', 'Missing', 'lucideCircleX'),
    complex: v('warning', 'Complex', 'lucideTriangleAlert'),
  },
  'proposal.decision': {
    pending: v('pending', 'Pending', 'lucideClock'),
    accepted: v('good', 'Accepted', 'lucideCircleCheck'),
    rejected: v('neutral', 'Rejected', 'lucideX'),
  },
  massing: {
    generating: v('pending', 'Generating', 'lucideLoaderCircle'),
    ready: v('good', 'Ready', 'lucideBox'),
    failed: v('bad', 'Failed', 'lucideCircleX'),
  },
  regulatory_import: {
    fetched: v('info', 'Fetched', 'lucideDownload'),
    importing: v('pending', 'Import running', 'lucideLoaderCircle'),
    done: v('good', 'Import finished', 'lucideCircleCheck'),
    failed: v('bad', 'Import failed', 'lucideCircleX'),
  },
  import_batch: {
    uploaded: v('neutral', 'Uploaded', 'lucideFileUp'),
    dry_run: v('info', 'Dry run', 'lucideFlaskConical'),
    applied: v('good', 'Applied', 'lucideCircleCheck'),
    discarded: v('neutral', 'Discarded', 'lucideTrash2'),
  },
  readiness: {
    ok: v('good', 'OK', 'lucideCircleCheck'),
    warning: v('warning', 'Warning', 'lucideTriangleAlert'),
    error: v('bad', 'Blocking', 'lucideCircleX'),
  },
  member: {
    active: v('good', 'Active', 'lucideCircleCheck'),
    suspended: v('bad', 'Suspended', 'lucideBan'),
    invited: v('pending', 'Invited', 'lucideMail'),
  },
  tenant: {
    active: v('good', 'Active', 'lucideCircleCheck'),
    disabled: v('bad', 'Disabled', 'lucideBan'),
    removed: v('neutral', 'Removed', 'lucideCircleX'),
  },
  project: {
    draft: v('pending', 'Draft', 'lucideCircleDashed'),
    active: v('good', 'Active', 'lucideCircleDot'),
    archived: v('neutral', 'Archived', 'lucideArchive'),
  },
  'building.placement': {
    unplaced: v('warning', 'Not placed', 'lucideMapPin'),
    draft: v('pending', 'Placement draft', 'lucideMapPin'),
    confirmed: v('good', 'Placed', 'lucideMapPin'),
  },
  // per-building construction status shown to buyers (ADR-0014 Decision 3)
  'building.construction': {
    planned: v('neutral', 'Planned', 'lucideClipboardList'),
    under_construction: v('warning', 'Under construction', 'lucideHardHat'),
    completed: v('good', 'Completed', 'lucideCircleCheck'),
  },
  publication: {
    preview: v('info', 'Preview', 'lucideEye'),
    published: v('good', 'Published', 'lucideGlobe'),
    retired: v('neutral', 'Retired', 'lucideHistory'),
  },
  media: {
    pending: v('pending', 'Uploading', 'lucideClock'),
    ready: v('good', 'Ready', 'lucideImage'),
  },
  // personal API tokens for assistants and scripts (ADR-0015)
  token: {
    active: v('good', 'Active', 'lucideCircleCheck'),
    expired: v('neutral', 'Expired', 'lucideClock'),
    revoked: v('bad', 'Revoked', 'lucideBan'),
  },
  'token.scope': {
    read: v('info', 'Read', 'lucideEye'),
    write: v('warning', 'Write', 'lucidePencil'),
  },
  role: {
    tenant_admin: v('info', 'Tenant admin', 'lucideShieldCheck'),
    project_manager: v('info', 'Project manager', 'lucideFolderKanban'),
    sales: v('info', 'Sales', 'lucideHandCoins'),
    architectural_reviewer: v('info', 'Architectural reviewer', 'lucideRuler'),
  },
  unit_type: {
    apartment: v('neutral', 'Apartment', 'lucideBuilding'),
    commercial: v('neutral', 'Commercial', 'lucideStore'),
    parking: v('neutral', 'Parking', 'lucideCar'),
    storage: v('neutral', 'Storage', 'lucideWarehouse'),
  },
  promotion_kind: {
    discount_percent: v('info', 'Percentage discount', 'lucidePercent'),
    discount_amount: v('info', 'Amount discount', 'lucideCoins'),
    gift: v('info', 'Gift', 'lucideGift'),
    financing: v('info', 'Financing', 'lucideHandCoins'),
    other: v('neutral', 'Other', 'lucideTag'),
  },
  lineage: {
    created: v('info', 'Created', 'lucidePlus'),
    relabelled: v('info', 'Relabelled', 'lucideTag'),
    split: v('warning', 'Split', 'lucideSplit'),
    merged: v('warning', 'Merged', 'lucideMerge'),
    removed: v('bad', 'Removed', 'lucideCircleX'),
  },
} satisfies Record<string, Table>;

export type StatusDomain = keyof typeof STATUS_TABLES;

const UNKNOWN_ICON = 'lucideCircleHelp';

/** Humanise an enum value the vocabulary does not know ("in_review" → "In review"). */
export function humanise(value: string): string {
  const s = value.replace(/[_-]+/g, ' ').trim();
  return s ? s[0].toUpperCase() + s.slice(1) : '';
}

/** Never throws: an unknown value renders neutral with the humanised raw text. */
export function statusOf(domain: StatusDomain, value: string | null | undefined): StatusView {
  if (value === null || value === undefined || value === '')
    return v('neutral', 'Unknown', UNKNOWN_ICON);
  const table = STATUS_TABLES[domain] as Table;
  return table[value] ?? v('neutral', humanise(String(value)), UNKNOWN_ICON);
}

export function labelOf(domain: StatusDomain, value: string | null | undefined): string {
  return statusOf(domain, value).label;
}

export function toneOf(domain: StatusDomain, value: string | null | undefined): Tone {
  return statusOf(domain, value).tone;
}

/** Chip markup as a string, for AG Grid cell renderers and other non-Angular hosts. */
export function statusChipHtml(domain: StatusDomain, value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '';
  const s = statusOf(domain, value);
  return `<span class="uf-chip uf-tone-${s.tone}">${iconSvg(s.icon)}${escapeHtml(s.label)}</span>`;
}

function escapeHtml(s: string): string {
  return s.replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string,
  );
}
