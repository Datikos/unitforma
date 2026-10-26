import { CellClassParams, ColDef, ValueFormatterParams } from 'ag-grid-community';
import { InventoryRow, PaymentPlanOut, SalesChanges, SalesSettingsOut } from 'api-client';
import { statusChipHtml, toneOf } from 'ui';
import { AVAILABILITY, formatPrice, parsePriceInput } from '../../sales/sales-format';

export type ColumnSet = 'commercial' | 'public' | 'internal' | 'all';

export interface Conflict {
  code: string;
  mine: SalesChanges;
  current: InventoryRow;
}

export const KEEP = '__keep__';
export const NONE = '__none__';

export interface BulkForm {
  availability: string;
  reason: string;
  price: string;
  adjust: number | null;
  currency: string;
  plan: string;
  promotions: string[];
  setPromotions: boolean;
  confirmZero: boolean;
}

export function blankBulk(): BulkForm {
  return {
    availability: KEEP,
    reason: '',
    price: '',
    adjust: null,
    currency: '',
    plan: KEEP,
    promotions: [],
    setPromotions: false,
    confirmZero: false,
  };
}

/** Columns per set; "all" shows every column. */
export const SETS: Record<Exclude<ColumnSet, 'all'>, string[]> = {
  commercial: [
    'code',
    'building_code',
    'floor_level',
    'unit_type',
    'layout',
    'wall_colour',
    'availability',
    'list_price',
    'currency',
    'price_on_request',
    'price_per_m2',
    'payment_plan_name',
    'promotion_names',
    'rooms',
    'bedrooms',
  ],
  public: [
    'code',
    'building_code',
    'floor_level',
    'unit_type',
    'availability',
    'list_price',
    'currency',
    'price_on_request',
    'price_per_m2',
    'payment_plan_name',
    'promotion_names',
    'rooms',
    'bedrooms',
    'bathrooms',
    'orientation',
    'entrance',
    'public_description',
    'media_count',
    'publication_status',
  ],
  internal: [
    'code',
    'building_code',
    'floor_level',
    'availability',
    'availability_reason',
    'list_price',
    'currency',
    'internal_notes',
    'verification_status',
    'publication_status',
    'version',
  ],
};

export const COLUMN_SET_LABELS: Record<ColumnSet, string> = {
  commercial: 'Commercial',
  public: 'Public fields',
  internal: 'Internal',
  all: 'All',
};

/** Which column ids a set shows, given every column the grid has. */
export function visibleColumns(set: ColumnSet, all: string[]): string[] {
  return set === 'all'
    ? all
    : all.filter((id) => SETS[set].includes(id) || (set === 'public' && id.startsWith('area_')));
}

export function showValue(obj: object, key: string): string {
  const v = (obj as Record<string, unknown>)[key];
  if (v === null || v === undefined || v === '') return '∅';
  return Array.isArray(v) ? v.join(', ') : String(v);
}

/** Grid cell → API change. Returns null when the column is not editable through the API. */
export function toChange(
  field: string,
  value: unknown,
  plans: PaymentPlanOut[],
): SalesChanges | null {
  switch (field) {
    case 'payment_plan_name': {
      const plan = plans.find((p) => p.name === value);
      return { payment_plan_id: plan ? plan.id : null };
    }
    case 'list_price':
      return { list_price: (value as string | null) ?? null };
    case 'rooms':
    case 'bedrooms':
    case 'bathrooms':
      return {
        [field]: value === null || value === undefined || value === '' ? null : Number(value),
      } as SalesChanges;
    case 'availability':
    case 'availability_reason':
    case 'currency':
    case 'price_on_request':
    case 'orientation':
    case 'layout':
    case 'wall_colour':
    case 'entrance':
    case 'public_description':
    case 'internal_notes':
      return { [field]: value === '' ? null : value } as SalesChanges;
    default:
      return null;
  }
}

/** The bulk form → API changes; `undefined` when the price is not a valid amount. */
export function bulkChanges(b: BulkForm): SalesChanges | undefined {
  const changes: SalesChanges = {};
  if (b.availability !== KEEP)
    changes.availability = b.availability as InventoryRow['availability'];
  if (b.price.trim()) {
    const p = parsePriceInput(b.price);
    if (p === undefined) return undefined;
    changes.list_price = p;
  }
  if (b.currency.trim()) changes.currency = b.currency.trim().toUpperCase();
  if (b.plan !== KEEP) changes.payment_plan_id = b.plan === NONE ? null : b.plan;
  if (b.setPromotions) changes.promotion_ids = b.promotions;
  return changes;
}

export interface ColumnDeps {
  settings: SalesSettingsOut | null;
  plans: () => PaymentPlanOut[];
  /** Codes of the project's layout registry (ADR-0022); the Layout cell picks from them. */
  layouts: () => string[];
  onBadPrice: (text: string) => void;
}

const chip =
  (domain: 'availability' | 'unit.verification' | 'unit.publication') => (p: { value?: unknown }) =>
    statusChipHtml(domain, p.value as string);

export function buildColumns(d: ColumnDeps): ColDef<InventoryRow>[] {
  const price = (p: ValueFormatterParams<InventoryRow>) =>
    formatPrice(p.value, p.data?.currency) ?? (p.data?.price_on_request ? 'on request' : '—');
  const num = (
    field: 'rooms' | 'bedrooms' | 'bathrooms',
    header: string,
  ): ColDef<InventoryRow> => ({
    field,
    headerName: header,
    editable: true,
    cellEditor: 'agNumberCellEditor',
    cellEditorParams: { min: 0, max: 100, precision: 0 },
    filter: 'agNumberColumnFilter',
    width: 105,
  });
  const areaKeys = (d.settings?.area_definitions ?? []).map(
    (a) => a as { key: string; label?: string },
  );
  return [
    {
      field: 'code',
      headerName: 'Code',
      pinned: 'left',
      width: 130,
      cellClass: 'uf-link',
      filter: 'agTextColumnFilter',
    },
    { field: 'building_code', headerName: 'Bldg', width: 90 },
    { field: 'floor_level', headerName: 'Floor', width: 95, filter: 'agNumberColumnFilter' },
    { field: 'unit_type', headerName: 'Type', width: 120 },
    {
      field: 'availability',
      headerName: 'Availability',
      editable: true,
      cellEditor: 'agSelectCellEditor',
      cellEditorParams: { values: [...AVAILABILITY] },
      width: 150,
      cellRenderer: chip('availability'),
      cellClassRules: {
        'uf-cell-good': (p: CellClassParams<InventoryRow>) =>
          toneOf('availability', p.value) === 'good',
        'uf-cell-bad': (p: CellClassParams<InventoryRow>) =>
          toneOf('availability', p.value) === 'bad',
      },
    },
    {
      field: 'availability_reason',
      headerName: 'Availability reason (internal)',
      editable: true,
      width: 200,
    },
    {
      field: 'list_price',
      headerName: 'Price',
      editable: true,
      type: 'rightAligned',
      width: 160,
      valueFormatter: price,
      valueParser: (p) => {
        const v = parsePriceInput(p.newValue);
        if (v === undefined) {
          d.onBadPrice(`"${p.newValue}" is not a price: use digits and at most two decimals`);
          return p.oldValue;
        }
        return v;
      },
      filter: 'agNumberColumnFilter',
      filterValueGetter: (p) => (p.data?.list_price == null ? null : Number(p.data.list_price)),
      comparator: (a, b) => (a == null ? -1 : Number(a)) - (b == null ? -1 : Number(b)),
    },
    {
      field: 'currency',
      headerName: 'Ccy',
      editable: true,
      width: 85,
      valueParser: (p) =>
        String(p.newValue ?? '')
          .trim()
          .toUpperCase() || p.oldValue,
    },
    {
      field: 'price_on_request',
      headerName: 'On request',
      editable: true,
      cellDataType: 'boolean',
      width: 115,
    },
    {
      field: 'price_per_m2',
      headerName: 'Price / m²',
      type: 'rightAligned',
      width: 140,
      valueFormatter: (p) => formatPrice(p.value, p.data?.currency) ?? '—',
      tooltipValueGetter: (p) =>
        p.data?.price_area_m2
          ? `per m² ${p.data.price_area_type} (${p.data.price_area_m2} m², ${p.data.price_area_source}, ${p.data.price_area_verified ? 'verified' : 'unverified'})`
          : `no ${p.data?.price_area_type} area`,
    },
    {
      field: 'payment_plan_name',
      headerName: 'Payment plan',
      editable: true,
      cellEditor: 'agSelectCellEditor',
      cellEditorParams: () => ({ values: ['', ...d.plans().map((p) => p.name)] }),
      width: 170,
    },
    {
      colId: 'promotion_names',
      headerName: 'Promotions',
      valueGetter: (p) => (p.data?.promotion_names ?? []).join(', '),
      width: 160,
    },
    num('rooms', 'Rooms'),
    num('bedrooms', 'Bedrooms'),
    num('bathrooms', 'Baths'),
    { field: 'orientation', headerName: 'Orientation', editable: true, width: 120 },
    {
      field: 'layout',
      headerName: 'Layout',
      editable: true,
      cellEditor: 'agSelectCellEditor',
      cellEditorParams: () => ({ values: ['', ...d.layouts()] }),
      width: 110,
      headerTooltip: 'Plan type from the Layouts registry; linked units share its media',
    },
    {
      field: 'wall_colour',
      headerName: 'Walls',
      editable: true,
      width: 110,
      headerTooltip: 'Wall finish: RAL code or hex colour; buyers see it',
    },
    { field: 'entrance', headerName: 'Entrance', editable: true, width: 110 },
    {
      field: 'public_description',
      headerName: 'Public description',
      editable: true,
      cellEditor: 'agLargeTextCellEditor',
      cellEditorPopup: true,
      width: 240,
    },
    {
      field: 'internal_notes',
      headerName: 'Internal notes',
      editable: true,
      cellEditor: 'agLargeTextCellEditor',
      cellEditorPopup: true,
      width: 240,
      headerTooltip: 'Never published',
    },
    {
      field: 'verification_status',
      headerName: 'Verification',
      width: 140,
      cellRenderer: chip('unit.verification'),
    },
    {
      field: 'publication_status',
      headerName: 'Publication',
      width: 140,
      cellRenderer: chip('unit.publication'),
    },
    ...areaKeys.map(
      (a) =>
        ({
          colId: `area_${a.key}`,
          headerName: `${a.label ?? a.key} m²`,
          valueGetter: (p: { data?: InventoryRow }) =>
            p.data?.areas?.[a.key] ? Number(p.data.areas[a.key]) : null,
          type: 'rightAligned',
          filter: 'agNumberColumnFilter',
          width: 140,
        }) as ColDef<InventoryRow>,
    ),
    { field: 'media_count', headerName: 'Media', width: 95, filter: 'agNumberColumnFilter' },
    { field: 'version', headerName: 'Ver.', width: 80 },
  ];
}
