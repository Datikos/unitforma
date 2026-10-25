# ADR-0009: One shell with a side menu, one design system for both apps

- **Status:** accepted (2026-10-25; implemented 2026-10-25)
- **Date:** 2026-10-25
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §11.1 (`libs/ui`: tokens, theming, layout primitives), §11.2 (admin screens),
  §11.3 (portal bundle budget), §11.4 (tenant branding as CSS custom properties), §7.5 (accessibility)

## Context

The owner's request on 2026-10-25: "the UX/UI are terrible, make it richer and polished, use colours
and a side menu". What the code showed on that day:

- The admin shell (`frontend/projects/admin/src/app/app.ts`) is one toolbar: brand, "Platform" link,
  e-mail, sign out. Navigation inside a tenant is a three-tab bar (Projects, Members, Audit log) and,
  on the project page, seven stroked buttons (Documents, Revision diffs, Site placement, 3D massing,
  Units, Inventory & prices, Publish). Imports and Sales setup are reachable only from Inventory, a
  sheet only from a Documents thumbnail. There are no breadcrumbs, no icons, no tooltips.
- All 20 admin pages carry inline templates and inline styles with hard-coded hex colours; the helper
  classes `.uf-form-row`, `.uf-row`, `.uf-toolbar`, `.uf-grid2` and `.uf-chip` (three different
  backgrounds) are redefined page by page. Statuses are printed as raw enum strings joined by "·"
  (`units.page.ts`: `lifecycle_status · verification_status · publication_status`).
  `window.confirm` is used four times and `window.prompt` three times; there are no toasts.
- The Material theme and the AG Grid theme ask for Roboto, which is never loaded. No icon set is
  installed; icons are Unicode glyphs (↑ ↓ ♥ ♡ ›).
- `frontend/projects/libs/ui` is the CLI placeholder ("ui works!") although plan §11.1 assigns it the
  design tokens, theming and layout primitives. `libs/domain-models` is a placeholder too; money and
  area formatters are duplicated in `admin/src/app/sales/sales-format.ts` and
  `portal/src/app/core/format.ts`.
- The portal has its own token set (`portal/src/styles.scss`: `--uf-primary`, `--uf-accent`, `--uf-bg`,
  …) overridden per tenant by `SiteStore.applyBranding()`, one shared component (`unit-card`), no
  header navigation and no help page.
- Build budgets (`angular.json`): `anyComponentStyle` warns at 4 kB and fails at 8 kB; `initial`
  warns at 500 kB. The portal's initial transfer size on 2026-10-25 is 80.88 kB (gzip estimate).
- No page in either app has a guide or help entry. 22 unit tests exist in 11 spec files; no admin page
  has a spec. `AGENTS.md` step 7 names `npx ng lint`, but ESLint is not installed and no `lint`
  target exists (known gap, unchanged by this ADR).
- Only `is_platform_admin` is gated in the UI; the four tenant roles are data on the Members page.

## Decision

1. **The admin app gets a persistent shell: top bar plus left side menu.** The menu has three
   sections: *Platform* (Tenants; platform admins only, the one gate the backend enforces),
   *Workspace* (a tenant switcher over the user's memberships, then Projects, Members, Audit log) and
   *Project* (shown while a project is open: Overview, Documents, Revision diffs, Site placement,
   3D massing, Units, Inventory, Import, Plans & promotions, Publish). Every entry has an icon.
   Below 1024 px the menu becomes an overlay drawer. Login and invitation pages render without the
   shell (route data `shell: 'bare'`).
2. **Routes nest into layouts, URLs do not change.** `t/:tenantId` loads a tenant shell component,
   `projects/:projectId` under it loads a project shell component; the leaf pages stay where they
   are. `paramsInheritanceStrategy: 'always'` so `tenantId` and `projectId` keep arriving as
   component inputs. Two root services, `TenantContext` and `ProjectContext`, load the entity header
   once per id and feed the menu, the breadcrumbs and the page headers; pages keep their own lists.
3. **One status vocabulary.** `statusOf(domain, value)` in `libs/ui` maps every status enum the UI
   shows (availability, unit lifecycle / verification / publication, document processing and kind
   source, sheet assignment and floor confirmation, proposal status / kind / decision, massing,
   regulatory import, import batch, publish readiness, member, tenant, project, building placement)
   to a tone (`good | warning | bad | info | neutral | pending`), a label and a Lucide icon. An
   unknown value renders neutral with the raw text and never throws. One `uf-status-chip` component
   renders it; AG Grid cells get the same icon and colour through a cell renderer that uses the same
   SVG string.
4. **Tokens live in `libs/ui` as CSS custom properties** (`--uf-font`, `--uf-primary`, `--uf-accent`,
   surfaces, text, border, radius, spacing and six tone triplets `--uf-tone-<tone>-{fg,bg,border}`).
   Both apps `@use` them through `stylePreprocessorOptions.includePaths`; `--uf-primary` and
   `--uf-accent` stay the pair the portal branding overrides. Page components keep no colour literals.
5. **Icons: Lucide through `@ng-icons`** (`@ng-icons/core` 36.1.0 MIT, `@ng-icons/lucide` 36.1.0 ISC),
   tree-shaken SVG registered once in `UF_ICONS`. **Font: Inter Variable with Noto Sans Georgian as
   fallback** (`@fontsource-variable/inter` 5.3.0, `@fontsource/noto-sans-georgian` 5.3.0, both
   OFL-1.1), self-hosted from the bundle, no Google Fonts CDN. Material typography and the AG Grid
   theme use the same `--uf-font` stack.
6. **Shared layout primitives in `libs/ui`, Material-free:** `uf-page-header` (title, headline facts,
   actions), `uf-status-chip`, `uf-empty-state` (what to do next), `uf-section-card` (collapsible,
   header carries a summary), `uf-facts` (key/value grid that marks set values), `uf-breadcrumbs`.
   Material-dependent pieces stay in the admin app: `ConfirmDialog`, `PromptDialog` (MatDialog) and a
   toast service (MatSnackBar) replace every `window.confirm` / `window.prompt`; results of actions are
   confirmed by a toast.
7. **The portal keeps its own small CSS system** (no Material, budget §11.3) but reads the shared
   tokens and the shared status vocabulary, gains a header with navigation (project, Units, Saved with
   a count), status badges with icons, richer unit cards, filter chips with "Clear all", a sticky unit
   action bar and a "How to use this portal" page.
8. **A guide ships with every screen.** `admin/src/app/guide/guide-content.ts` holds one entry per
   route key (purpose, controls, which role the backend accepts, what waits for whom); a drawer in the
   shell shows the entry of the current page, `/guide` shows the whole manual.
9. **Pages longer than about 300 lines are split** into model (types, pure functions), store (signals
   and API calls) and view (template and component), starting with inventory, sheet and unit sales.
10. **Gates:** `npx ng build admin` and `npx ng build portal` with 0 warnings (the 4 kB component style
    budget included), `npx ng test --watch=false` green per project, portal initial transfer size
    reported against the 80.88 kB baseline.

## Options considered

- **Icons. O1 (chosen) `@ng-icons/lucide`, tree-shaken SVG.** Pros: only used icons ship, the same
  SVG string works in templates and inside AG Grid cells, MIT/ISC. Cons: a new dependency pair.
  **O2 `material-symbols` font.** Pros: one import. Cons: about 300 kB of font, ligature text flashes
  before the font arrives, a second mechanism for grid cells. **O3 keep Unicode glyphs.** Fails "an
  icon from one vocabulary".
- **Font. O1 (chosen) Inter Variable + Noto Sans Georgian.** Pros: UI face with tabular numerals for
  grids and prices, Georgian unit labels and tenant text covered, self-hosted. Cons: two font packages,
  about 120 kB of woff2 (outside the `initial` budget, cached). **O2 Noto Sans only.** Heavier Latin,
  less distinct. **O3 system-ui.** Renders differently on the owner's Mac and Windows box, and he
  judges by screenshot.
- **Where tokens and components live. O1 (chosen) `libs/ui` without Material, Material pieces in the
  admin app.** Plan §11.1 says so; the portal must not pull Material through a barrel. **O2 everything
  in `libs/ui` with Material as a peer.** Portal budget at risk. **O3 per app.** Repeats today's
  duplication.
- **Side menu. O1 (chosen) `MatSidenav` + `BreakpointObserver`.** Backdrop, focus trap, Escape and the
  over/side modes come with the package that is already in the bundle. **O2 hand-rolled CSS grid
  drawer.** Re-implements the accessibility of a drawer for no gain.
- **Portal styling. O1 (chosen) keep the token-driven CSS, share tokens and vocabulary.** **O2 adopt
  Material in the portal.** About 150 kB more and a theme the tenant palette cannot override cleanly.

## Trade-off analysis

| Axis | Lucide SVG | Symbols font | Inter + Noto Georgian | system-ui | MatSidenav | hand-rolled |
|---|---|---|---|---|---|---|
| Added transfer | a few kB | ~300 kB | ~120 kB fonts, cached | 0 | 0 (already bundled) | 0 |
| Works inside AG Grid cells | yes, same SVG | needs a second path | n/a | n/a | n/a | n/a |
| Georgian text | n/a | n/a | yes | yes, OS dependent | n/a | n/a |
| Same look on Mac and Windows | yes | yes | yes | no | yes | yes |
| Accessibility work | none | none | none | none | none | focus trap, Escape, aria |

## Consequences

**Easier.** Every status reads the same on every page and in the grid. A new page is composed from
`uf-page-header`, `uf-section-card`, `uf-status-chip` and `uf-empty-state`. Any page is one click away
from the menu; breadcrumbs say where the user is. The guide answers "what does this screen do" without
leaving it.

**Harder.** Two rules on every frontend review: no colour literal in a page style, no raw enum in a
template (use `statusOf`). `libs/ui` is a dependency of both apps, so a change there is built twice.
`paramsInheritanceStrategy: 'always'` also merges route `data`, which the guide and breadcrumb keys
rely on; a leaf without its own key inherits the parent's.

**Operations.** Four npm packages with an online resolve at install; licences MIT, ISC and OFL-1.1
(AGENTS.md rule 9). Nothing changes in images or Compose.

**Revisit.** The plan-viewer polygon colours (`libs/plan-viewer`) and the portal's SVG/3D availability
colours (`portal/src/app/core/format.ts`) stay in TypeScript and must equal the tone tokens by value;
reading them from `getComputedStyle` is a later step. A tenant Dashboard page (plan §11.2) and
role-aware menus wait for the backend to enforce roles. ESLint and the `lint` target are a separate
item.

**Out of scope here:** i18n and a runtime language switch (plan §A3: English UI in the MVP), dark
mode, leads and inquiries (Phase 5), ESLint setup, role gating beyond `is_platform_admin`.

## Action items

Phase 1, shell and design system
- [x] 1 Dependencies `@ng-icons/core`, `@ng-icons/lucide`, `@fontsource-variable/inter`,
      `@fontsource/noto-sans-georgian`; `angular.json` `includePaths` for `libs/ui/src/styles`.
- [x] 2 `libs/ui`: `styles/_tokens.scss`, `styles/_primitives.scss`, `lib/icons.ts` (`UF_ICONS`),
      `lib/status.ts` (`statusOf`, `statusCellRenderer`), `uf-status-chip`, `uf-empty-state`,
      `uf-page-header`, `uf-section-card`, `uf-facts`, `uf-breadcrumbs`; placeholder `ui.ts` removed;
      `status.spec.ts`.
- [x] 3 Admin shell: `app.ts` with `MatSidenav`, `shell/side-menu.component.ts`, `shell/menu.model.ts`,
      `shell/tenant-shell.component.ts`, `shell/project-shell.component.ts`,
      `core/tenant-context.ts`, `core/project-context.ts`, `core/breadcrumbs.store.ts`; routes nested;
      `paramsInheritanceStrategy: 'always'`; dead `app.html` / `app.scss` and `tenant-shell.page.ts`
      removed; `styles.scss` with fonts, tokens, theme typography; AG Grid font aligned.
- [x] 4 Admin `ui/`: `ConfirmDialogComponent`, `PromptDialogComponent`, `DialogsService`,
      `ToastService`; every `window.confirm` / `window.prompt` replaced.

Phase 2, admin pages
- [x] 5 Inventory split into `pages/inventory/` (model, store, view, conflict card); chips in cells,
      headline facts, dialogs, toasts, empty state.
- [x] 6 Sheet split into `pages/sheet/` (model, store, view); floor chips, mode hints, dialogs.
- [x] 7 Unit sales split into `pages/unit-sales/` (model, store, view, media, history); collapsible
      sections with summaries, changed-field marking, header facts.
- [x] 8 Project overview, Projects, Publish, Documents (shell level only), Members, Audit, Units,
      Proposals, Proposal, Placement, Massing, Import, Sales setup, Home, Platform tenants, Login,
      Invite: page header, chips, labels, filters past 20 rows, empty states, collapsible sections.

Phase 3, portal
- [x] 9 Tokens from `libs/ui`, `uf-portal-header` with project, Units and Saved count, status badges
      with icons, richer `unit-card`, filter chips with Clear all and result count, sticky unit action
      bar, skeletons, empty states, 760 px pass; transfer size reported.

Phase 4, guide, tests and docs
- [x] 10 `guide/guide-content.ts`, `guide-drawer.component.ts`, `/guide` route; portal `how-to-use`
      page and footer link.
- [x] 11 Specs: status vocabulary coverage, menu model, tenant context loads once, breadcrumbs,
      project shell input binding, dialogs, portal header count; counts reported.
- [x] 12 Docs: `frontend/README.md` (libraries table, fonts and icons, `includePaths`, lint gap),
      plan §11.1, §11.2, §11.4, root README status line.
      *Found while implementing (2026-10-25):* the side menu's two `<select>` controls first pulled
      `@angular/forms` (57 kB raw) into the initial bundle; plain `(change)` bindings keep the admin
      initial bundle at 484.8 kB raw (120.1 kB transfer), under the 500 kB budget. The guide drawer
      is `@defer`red so the guide text loads on first open. Portal initial transfer grew from 80.9 kB
      to 93.5 kB (chips, icons, header). Frontend tests went from 22 to 34 (`ui` 5, `admin` 17,
      `portal` 8, `plan-viewer` 3, `viewer-3d` 1). The plan-viewer polygon colours and the portal's
      `AVAILABILITY` fill/stroke values still live in TypeScript and equal the tone tokens by value.
