# Unitforma frontend

Angular 22 CLI workspace (standalone components, signals, zoneless).

| Project | Type | Purpose |
|---|---|---|
| `admin` | application | Developer administration and sales workspace (`app.unitforma.com`), container `web-admin` |
| `portal` | application | Buyer portals on `{tenant}.unitforma.com` and custom domains, container `web-portal` |
| `libs/api-client` | library | Generated from the backend OpenAPI document (do not hand-edit) |
| `libs/auth-staff` | library | Kratos browser-flow UI renderer and staff session guard |
| `libs/auth-buyer` | library | Email-code modal talking to the `/auth/*` backend-for-frontend |
| `libs/ui` | library | Design system (ADR-0009): tokens in `src/styles/_tokens.scss`, primitives in `_primitives.scss`, the status vocabulary (`statusOf`), icons (`UF_ICONS`, Lucide via `@ng-icons`), and the Material-free components `uf-status-chip`, `uf-page-header`, `uf-section-card`, `uf-facts`, `uf-empty-state`, `uf-breadcrumbs` |
| `libs/plan-viewer` | library | Deep-zoom plan tiles with SVG polygon overlay (view and edit modes) |
| `libs/viewer-3d` | library | three.js wrapper: GLB loading, picking, highlight, capability detection and fallbacks |
| `libs/domain-models` | library | Placeholder. Formatters still live in `admin/src/app/sales/sales-format.ts` and `portal/src/app/core/format.ts` (known gap) |

```bash
npm ci
npx ng serve admin      # http://localhost:4200
npx ng serve portal --port 4201
npx ng test admin --watch=false && npx ng test portal --watch=false
npx ng build admin --configuration production && npx ng build portal --configuration production
```

Docker images: `Dockerfile.admin`, `Dockerfile.portal` (multi-stage build → unprivileged nginx on 8080).
Requires Node 24 (Angular 22 needs `^22.22.3 || ^24.15 || ^26`).

## Design system (ADR-0009)

- **Tokens** are CSS custom properties (`--uf-*`) defined once in `projects/libs/ui/src/styles/_tokens.scss`; both apps `@use 'tokens'` and `@use 'primitives'` through `stylePreprocessorOptions.includePaths` in `angular.json`. The portal's tenant branding overrides `--uf-primary` and `--uf-accent` at runtime (plan §11.4).
- **Status vocabulary**: every status enum the UI shows maps to a tone (`good | warning | bad | info | neutral | pending`), a label and an icon in `projects/libs/ui/src/lib/status.ts`. Templates use `<uf-status-chip domain="…" [value]="…">`; AG Grid cells use `statusChipHtml()`. Rule for reviews: no colour literal in a page style, no raw enum in a template.
- **Fonts and icons** are self-hosted from npm, no CDN: Inter Variable and Noto Sans Georgian (`@fontsource-variable/inter`, `@fontsource/noto-sans-georgian`, OFL-1.1) are listed in the `styles` array of both apps; icons are Lucide SVGs (`@ng-icons/lucide`, ISC) registered in `UF_ICONS` and tree-shaken.
- **Admin shell**: `app.ts` holds the side menu (`shell/side-menu.component.ts`, menu built by `shell/menu.model.ts`), the top bar with breadcrumbs and the guide drawer. Routes nest `t/:tenantId` (tenant shell) → `projects/:projectId` (project shell) → pages; `paramsInheritanceStrategy: 'always'` keeps `tenantId`/`projectId` arriving as component inputs. `core/tenant-context.ts` and `core/project-context.ts` load the headers once; `core/route-info.ts` exposes the route `data` keys `guide`, `breadcrumb`, `shell`.
- **Dialogs and toasts** (`admin/src/app/ui/`): `DialogsService.confirm/prompt` (MatDialog) and `ToastService` (MatSnackBar) replace `window.confirm`/`window.prompt`.
- **Guide**: one entry per admin route in `admin/src/app/guide/guide-content.ts`, shown in the shell's drawer and at `/guide`; the portal's "How to use this portal" is `portal/src/app/guide/portal-guide.ts` at `/how-to-use`. Edit the entry together with the screen.
- **Portal richness (ADR-0016)**: `portal-api.ts` carries `gallery[]`, `site.features[]` (ring on the site sheet plus `ring_m`), `address.lat/lng`, `layout` and `media[].shared_from`; `libs/viewer-3d` draws the features (grass, paving, generic trees) on a ground disc with a sky gradient and shadows, and `libs/plan-viewer` takes a `focus` ring. The project page's lightbox styles live in `portal/src/styles.scss` because of the component budget; the map is an OpenStreetMap iframe with the attribution line (linked to openstreetmap.org/copyright), no script; `UF_PORTAL_MAP_EMBED=false` on the API turns the iframe off and leaves the address and the link (ADR-0016 E4). The admin placement page stores facade choices per building (`PATCH /buildings/{id}` `facades`, ADR-0016 E3) and site features as rings normalised to the site sheet; the dark side menu is painted through Material's `--mat-sidenav-container-*` tokens in `admin/src/styles/_shell.scss`.
- **ADR-0017**: `libs/plan-viewer` draws the selected unit as an overlay (halo + outline) after the polygons because the availability colours are inline styles; `libs/viewer-3d` reads the glTF material role (`roof | wall | facade`) from `material.userData` and takes `tintMode` (`availability` tints walls and facades at 45 %, `neutral` leaves drawings pure); the admin unit page has `unit-renders.component.ts` (generated 3D plan renders with review) and the project menu starts with `pages/setup.page.ts` (the checklist from `GET /projects/{id}/setup`).
- **ADR-0018 / owner's items of 2026-10-26**: `libs/plan-viewer` has a toolbar (zoom, fit, full screen), a `callout` input with a `[callout]` content slot anchored at a polygon, `locked` polygons, and labels sized per polygon (`labelFontSize`: the sheet size `width / 60`, shrunk until the text fits the polygon's bounding box at 0.6 em per glyph, with the white halo at 0.2 em, so "P-10" stays inside a 2.5 m parking stall); the portal building page uses the callout for the selected unit, the unit page uses move mode for the furniture ruler. The project document's availability and stats are overlaid live by the API; the portal needs nothing for it.
- **Density**: the admin theme runs at Material density −2 (fields 48 px, buttons 36 px) since the owner's review of 2026-10-26; `.uf-form-row` aligns its items at the top so a hint under one field does not push the others, and buttons in a row carry a 6 px top margin to sit centred against a field.
- **Compact cards**: `uf-section-card` headers and bodies carry less padding since 2026-10-26, and the unit page packs its rows (price with its two checkboxes, terms in the same card, room fields that share rows, description next to notes, buyer toggles in two columns); the page went from 2357 px to 1769 px at 1440 px width.
- **Budgets** (`angular.json`, production): initial 500 kB warning for both apps, 4 kB per component style; shared styles belong in the global stylesheet or `libs/ui`, not in a component. Measured 2026-10-25: admin initial 484.8 kB raw / 120.1 kB transfer, portal 361.7 kB raw / 93.5 kB transfer (3D chunk lazy).
- **Known gap**: `AGENTS.md` names `npx ng lint`, but ESLint is not installed and there is no `lint` target; Prettier (`.prettierrc`) is the only formatter.

## Development against the backend

`npx ng serve admin --proxy-config proxy.conf.json` forwards `/api`, `/internal` to the API on
port 8000 and `/.ory` to Kratos on 4433, mirroring the Caddy routing. Regenerate the typed client
after API changes with `npm run api:generate` (reads `projects/libs/api-client/src/generated/openapi.json`).
