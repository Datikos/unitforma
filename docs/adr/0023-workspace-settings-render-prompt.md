# ADR-0023: A workspace Settings page; the base prompt of generated plan renders is its first setting

- **Status:** accepted (2026-10-26, the owner's "set it in the global settings. if there is no page like it, let's make"; implemented 2026-10-26)
- **Date:** 2026-10-26
- **Deciders:** David Sakhelashvili (platform owner)
- **Plan reference:** §11.2 (tenant screens: "Settings"), §12.3 (`renders.generate`), ADR-0017 Decision 4 (the prompt fixed in code, amended here), ADR-0022 Decision 4 (layout renders)

## Context

ADR-0017 Decision 4 fixed the render prompt in code: `renders/service.PROMPT` (isometric cutaway,
keep the drawn walls, furnish by room function, light wooden floors, white walls, white background,
no text) plus, appended in this order, the joined-apartment sentence (E4), "The walls are painted
..." from `units.attributes.wall_colour` (E5) and the staff member's note. Verified on 2026-10-26:

- The first live renders were judged the same day. Changing the style for every apartment (floor
  material, camera angle, light) means a release, since the text lives in a Python constant.
- The owner asked on 2026-10-26 for "a general prompt for Gemini apartment image generation" and
  chose the workspace level ("set it in the global settings") over a project-level field.
- `tenants.settings jsonb` exists since Phase 1 and is empty. `PATCH /tenants/{id}` writes it whole
  (`setattr`, no merge) behind the `tenant.settings` write right (tenant admin only, `authz.py`).
- Plan §11.2 lists a tenant "Settings" screen (area definitions defaults, consent texts, retention)
  that was never built; the Workspace menu has Projects, Members, API tokens, Audit log.
- `unit_renders.prompt` stores the final text of every request, so what was sent stays auditable
  whatever the source of the base text.

## Decision

1. **`tenants.settings.render_prompt` is the base prompt of generated plan renders.** A string of 1 to
   4000 characters or absent. When present it replaces `PROMPT`; the joined-apartment sentence, the
   wall colour and the note are still appended by the code, in that order, so the workspace never
   re-adds them. Empty or whitespace means absent (the code default).
2. **Two endpoints on the renders router**, behind the `tenant.settings` right: `GET
   /tenants/{id}/render-prompt` returns `{default, prompt, source}` (`source` is `workspace` or
   `default`); `PUT /tenants/{id}/render-prompt` takes `{prompt}` (`null` clears), merges the key
   into `settings`, writes an audit row (`entity_type = tenant`, `action = render_prompt`) and
   returns the same shape. `PATCH /tenants/{id}` now merges `settings` into the stored dict instead of
   replacing it, so a later page cannot wipe this key by accident; `branding` stays replace-whole,
   since the Publish page clears a logo or colour by sending the dict without that key.
3. **The admin app gets a "Settings" page** at `t/:tenantId/settings`, last in the Workspace menu
   before Audit log, with one card "Generated plan renders": a textarea pre-filled with the current
   text (the default when nothing is set), a "source" chip, Save, and "Reset to default" (clears the
   key after a confirmation). The guide entry names the tenant admin as the only writer and warns
   that removing "keep the exact wall layout ... no text, no labels" is what makes renders unusable.
4. **The request reads the setting, not the job.** `renders.service.request_render` loads the
   tenant row in the same session and composes the prompt at request time; `renders.generate` keeps
   sending `unit_renders.prompt` as stored. A change on the Settings page applies to the next
   request, never to a queued one.

## Options considered

### Option A: edit the constant in code
Pro: nothing to build. Con: every wording change is a release; the owner cannot tune the style
himself.

### Option B: deployment setting `UF_AI_IMAGE_PROMPT`
Pro: one line in `core/settings.py`. Con: one text for every tenant, a restart per change, the
operator edits it rather than the workspace admin.

### Option C: workspace setting in `tenants.settings`, a Settings page (chosen)
Pro: no migration, the tenant admin edits it on a screen, the audit log shows every change, the
page the plan already names starts to exist. Con: one style per workspace; a project that wants
another style has only the per-request note.

### Option D: project-level field in `projects.sales_settings`
Pro: a style per project. Con: the owner has one style in mind; a second place to look for the
prompt; the project page is already dense.

## Trade-off analysis

| | A | B | C | D |
|---|---|---|---|---|
| Owner edits it himself | no | no (operator) | yes | yes |
| Granularity | global | deployment | workspace | project |
| Migration | — | — | none (jsonb key) | none (jsonb key) |
| Audit of the change | git | none | audit row | audit row |
| Size | S | S | S | S to M |

## Consequences

Easier: the style of every generated render is one text on one page; a wording experiment costs
one request (0.0336 USD) and no release; the Settings page exists for the next tenant-level setting.

Harder: a prompt that drops the layout constraints produces images the reviewer must reject, and
only the guide warns; the text goes outbound to the image provider, so it is capped at 4000
characters and never contains secrets by construction (plain text typed by a tenant admin).

Revisit: a per-project override (Option D) if a second style is ever wanted; a preview of the
composed prompt on the unit's render panel.

**Out of scope here:** branding, retention and consent settings on the same page (plan §11.2);
a prompt per media kind (exterior, interior; ADR-0017 out of scope); a prompt per project.

## Action items

### Phase A: backend

- [x] A1 `api/schemas.py`: `RenderPromptOut`, `RenderPromptUpdate` (1 to 4000 characters or null).
- [x] A2 `api/admin_renders.py`: `GET` and `PUT /tenants/{id}/render-prompt` (`tenant.settings`
      read and write), merge into `settings`, audit row.
- [x] A3 `renders/service.py`: `base_prompt(tenant)` and its use in `request_render`.
- [x] A4 `api/admin.py` `update_tenant`: merge `settings` (not `branding`).
- [x] A5 Tests in `test_unit_renders.py`: read default, set a custom prompt, the next request starts
      with it and still ends with the note, reset returns the default, 422 above 4000 characters,
      403 for `sales`; `PATCH /tenants/{id}` keeps the key.

### Phase B: admin app

- [x] B1 `api-client`: `getRenderPrompt`, `setRenderPrompt`; regenerated `openapi.d.ts`.
- [x] B2 `pages/settings.page.ts`, route `settings` (`data.guide: 'settings'`), Workspace menu
      item "Settings" (`lucideSettings`), guide entry.

### Phase C: docs

- [x] C1 ADR-0017 Decision 4 amended; README status sentence; this ADR.
