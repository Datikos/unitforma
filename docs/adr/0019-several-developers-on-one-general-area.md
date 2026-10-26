# ADR-0019: Several developers building on one general area

- **Status:** proposed (2026-10-26); waits for the owner's pick between Option A and Option B
- **Date:** 2026-10-26
- **Deciders:** David Sakhelashvili (platform owner): which option, who operates the shared portal host, whether buyers see the developer's name per building
- **Plan reference:** §3.1 (tenancy), §3.3 (routing), §3.4 (authorization), §7.1 (navigation model), §11.3 (portal screens), ADR-0003 (hosts), ADR-0016 (site plan and features)

## Context

The owner described the case on 2026-10-26: "there are cases when different legal entity are developing
same area, on the one general area". One general plan (გენგეგმა), several houses, each built and sold by
a different company, and buyers who think of the whole area as one place. What the code offers today:

- A tenant is one developer: its own portal host (`<slug>.<platform>` or a custom domain, ADR-0003), its
  branding (name, colours, sales e-mail and phone), its members, its audit log, row-level security on
  every table. A project belongs to one tenant; a permit import creates one project with its buildings.
- Members can be restricted to projects (`memberships.all_projects = false`, `project_ids`;
  `TenantContext.require_project`), so staff of one company can be kept to their own project inside a
  tenant. Branding and contacts are per tenant, not per project.
- A project has one site plan with every building of the project placed on it and the public site
  features (ADR-0016). The portal project page shows all buildings of the project on that plan and in 3D.
- The portal site page lists the tenant's published projects; nothing links projects of different
  tenants, and no page aggregates them.

## Options considered

### Option A: one tenant per area, one project per developer or house, members restricted to their project

The area operator (or the lead developer) owns the tenant and the portal host; each company's staff get
memberships limited to their project(s). Missing today: contacts and a short developer name per project
(shown on the project page and the building cards), and the site page already lists the projects.
Pros: nothing new in routing, security or publishing; the area is one portal with one site plan per
project (or one project with every house placed on the shared plan when one company sells for all);
a few days of work. Cons: one legal entity holds the tenant (billing, data owner); the other
companies' staff see the shared tenant's name in the admin shell; audit rows of all companies in one
log (filtered by project).

### Option B: a platform-level area that aggregates publications of several tenants

A new entity `areas` (name, host, general plan, placements of each member project with that tenant's
consent). The area host serves a combined site page: one plan with every house, each unit opening on
its own tenant's portal host. Pros: each company keeps its own tenant, billing, data and audit; the
area page is read-only aggregation of published data (nothing written across tenants). Cons: a new
table, host routing and certificate for area hosts, consent and placement workflow for the area owner,
cross-tenant reads under the platform scope, a combined read model or live aggregation of several
publications; a week or more.

### Option C: nothing shared; each developer's portal stands alone

The OpenStreetMap embed shows the surroundings. Rejected: the owner asked for the shared area.

## Trade-off analysis

| Axis | A one tenant | B platform area | C nothing |
|---|---|---|---|
| New code | per-project contacts and developer name (S) | areas table, host routing, consent, aggregation (L) | 0 |
| Legal separation of the companies | no (one tenant) | yes | yes |
| One page for the whole area | yes | yes | no |
| Who operates it | the tenant admin | the area owner on the platform | — |
| Risk | the shared tenant's admin can see everything | cross-tenant reads must stay read-only and consented | — |

## Recommendation

Option A first: it needs only per-project contacts and a developer label, and it fits the case where
one company markets the area or the companies trust one operator. Option B when two companies insist on
separate accounts for billing or legal reasons; its design starts from this ADR.

## Decision

Open. The owner picks:

1. Option A or Option B.
2. Who operates the shared host (one of the developers, or a company of the area).
3. Whether the developer's name appears on building cards and unit pages.

## Action items (Option A, written so they can start on the pick)

- [ ] A1 `projects.portal_settings.contact` (developer name, sales e-mail, phone) edited on the Publish
      page, shown on the project page and the unit page instead of the tenant's contacts when set.
- [ ] A2 Building cards and the site page show the developer name when the project has one.
- [ ] A3 Guide entries, plan §9.3, README.
- [ ] A4 A test on the publishing world: project contacts in the snapshot, tenant contacts as fallback.
