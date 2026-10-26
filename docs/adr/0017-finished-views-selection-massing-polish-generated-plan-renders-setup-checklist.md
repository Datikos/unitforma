# ADR-0017: Finished views for buyers: selection highlight on the plan, neutral massing with facades, AI-generated 3D plan renders under staff review, and a setup checklist

- **Status:** accepted (2026-10-26; implemented 2026-10-26; first live renders approved and published the same day; E2 (architect's IFC) and E3 (second provider) open; the sharing of an approved render by layout code is replaced by a render owned by the layout, ADR-0022 Decision 4)
- **Date:** 2026-10-26
- **Deciders:** David Sakhelashvili (platform owner); he decided on 2026-10-26 that AI-generated images may be shown when a staff member has reviewed them and buyers see a "generated" label (closes ADR-0016 E2)
- **Plan reference:** §5.3 (unit media, AI disclosure), §7.3 (3D and fallbacks), §11.2 (admin screens), §11.3 (portal screens), §12.3 (jobs), §21 (sources), ADR-0004 (`is_ai_generated`), ADR-0006 C (IFC model), ADR-0009 (design system), ADR-0016 (gallery, facades, layout-shared media)

## Context

After ADR-0016 the owner looked at the sample project (`permit-1127975`, published v6) and asked for four
things on 2026-10-26: setup is still complicated; the 3D facade is a drawing, not "finished like a render";
nothing is highlighted on the floor plan when an apartment is selected; and a selected apartment should show a
finished view like the furnished isometric cutaway ("dollhouse") image he attached. What the code does today:

- `libs/plan-viewer` paints every polygon with `[style.fill]`/`[style.stroke]` from the availability colour.
  Inline styles beat the `.pv__poly--selected` class, so the selected unit looks like its neighbours. The
  admin sheet store and the portal building page both pass `selected: true`; only the paint is missing.
- `geometry/massing.py` extrudes each unit into one mesh: walls and both caps share one material per unit
  type, and the portal tints the whole mesh by availability (`unitColors`). With four facade drawings mapped,
  almost every outer wall is textured, so the availability colour is left on the roofs, which is what the
  owner sees from above: a green box with drawings on the sides.
- Unit media already has `kind = plan_render`, `is_ai_generated`, `ai_disclosure_text` and the portal label
  "Illustrative — AI generated" (ADR-0004); ADR-0016 Decision 4 shares a unit's media with every unit of the
  same layout code. Nothing generates an image: the developer must upload one per layout.
- Setup needs eight screens in a fixed order (documents, floors, mapping, site plan, placement, facades,
  prices, publish) and the only overview is the readiness list on the Publish page. On 2026-10-26 the
  assistant configured the sample project through the API because the order was not visible on any screen.
- The architect's own 3D model is the real answer to "finished like a render": the IFC pipeline exists
  (ADR-0006 Phase C) and shows the model instead of the massing. The permit's drawing set had an ArchiCAD
  `model.pla`, which the import skips; the developer has to ask the architect for an IFC export.
- The migration chain is free again: `0013_api_tokens` is in `main` and the dev database is at 0013.

Third-party facts (read on 2026-10-26 from ai.google.dev, pages dated 2026-10-22; details in plan §21):

- Gemini image generation and editing go through `POST https://generativelanguage.googleapis.com/v1beta/interactions`
  with header `x-goog-api-key`, a body `{"model", "input": [{"type": "text", "text"}, {"type": "image",
  "mime_type", "data": <base64>}], "response_format": {"type": "image", "mime_type", "aspect_ratio",
  "image_size": "1K"}}` (uppercase K). The current workhorse model is `gemini-nano-banana-2.1` (GA
  2026-10-06, no shutdown date), billed at $30 per 1M image output tokens, "equivalent to $0.0336 per 1K
  image" plus input at $1.50 per 1M tokens; `gemini-3.1-flash-lite-image` costs the same per 1K image;
  `gemini-2.5-flash-image` is deprecated (the pricing page says shut down 2026-10-02, the deprecations page
  says 2027-03-15: unresolved). "All generated images include a SynthID watermark." The raw JSON response
  shape is **not documented** on the pages read (the SDK exposes `output_image.data`; the REST response holds
  `steps[]` with `{type: "image", data}` blocks), so the client parses defensively and records the top-level
  keys of an unexpected answer in the request's error.
- OpenAI's image models bill output tokens too (GPT Image 2 at $30 per 1M output tokens, about $0.006 to
  $0.21 per 1024 px image by quality, input images extra); model names changed twice in 2026 and the
  gpt-image-1 family shuts down in late 2026. Third-party figures, **unverified**.
- three.js `GLTFLoader` turns a glTF mesh with several primitives into a `Group` with one child `Mesh` per
  primitive and copies glTF `extras` into `userData` (viewer code already relies on the first fact).

## Decision

1. **The selected unit is drawn on top.** `libs/plan-viewer` draws one overlay polygon after the loop for
   the polygon with `selected: true`: a white halo under a 3-px dark stroke, `pointer-events: none`, so it
   wins over the inline availability colours; while a selection exists the host gets `pv--has-selection`
   and the other unit polygons fade to 55 %; the selected label is bold and one step larger. The same
   component serves the portal building page, the unit page and the admin sheet editor. A spec covers it.
2. **Roofs are neutral and the viewer tints only what should carry status.** The GLB emits each unit's caps
   as their own primitive with a "roof" material (light grey) and tags every material with
   `extras.role = roof | wall | facade`. The viewer never tints roof materials with `unitColors`; facade
   (textured) materials are tinted at 45 % in availability mode and left untinted in neutral mode; plain
   walls take the availability colour or, in neutral mode, a warm light grey. A new input `tintMode:
   'availability' | 'neutral'`; the portal project and unit pages default to neutral with a toggle
   "Availability colours", the building page (where the colour picks the unit) defaults to availability;
   the admin massing page keeps availability with drafts translucent. Hover and selection paint as before.
3. **A staff member can generate a 3D plan render of a unit, review it, and publish it.** New table
   `unit_renders` (migration `0014`, RLS): id, tenant_id, project_id, unit_id, `status` (queued | running |
   review | approved | rejected | failed), `provider`, `model`, `prompt`, `input_key` (the plan crop sent),
   `media_id` (→ `unit_media`, SET NULL), `error`, `cost_usd`, `requested_by`, `reviewed_by`, timestamps.
   `POST /units/{id}/renders` (write on the `sales` resource, like unit media) crops the unit's current outline from its sheet raster
   (bounding box plus 8 %, everything outside the ring painted white, at most 1536 px), stores the crop,
   writes the row and defers `renders.generate` on the `docs` queue; it answers 409 when no provider is
   configured or the unit has no outline, 429 past the tenant's daily cap. The worker reads the inputs,
   closes its session, calls the provider, reopens a session and stores the result as a `unit_media` row:
   `kind = plan_render`, `is_ai_generated = true`, `ai_disclosure_text` = "Generated from the floor plan by
   AI — furniture and finishes are illustrative", `is_public = false`. `POST /renders/{id}/approve` sets
   `is_public = true` (the render then serves every unit with the same layout code, ADR-0016 Decision 4);
   `POST /renders/{id}/reject` deletes the media. Every step writes an audit row. The portal shows the
   existing label on generated media; nothing reaches buyers before approval.
4. **One provider behind an interface, configured, never hard-coded.** `renders/provider.py` defines
   `ImageProvider.edit(image, mime, prompt) -> GeneratedImage`; `renders/gemini.py` implements it with
   `httpx` against one fixed host. Settings: `UF_AI_IMAGE_PROVIDER` (`none` | `gemini`, default `none`:
   the button is disabled and the hint names the setting), `UF_AI_IMAGE_API_KEY` (file secret
   `ai_image_api_key`, mounted on api and workers), `UF_AI_IMAGE_MODEL` (default `gemini-nano-banana-2.1`),
   `UF_AI_IMAGE_ENDPOINT`, `UF_AI_IMAGE_DAILY_LIMIT` per tenant (default 40), `UF_AI_IMAGE_COST_PER_IMAGE_USD`
   (default 0.0336, shown on the button, source in plan §21). The prompt is fixed in code (keep the drawn
   layout, furnish by room function, white background, no text) plus an optional note from the staff member.
5. **A setup checklist page shows the order of work and what is missing.** `GET /projects/{id}/setup`
   returns ordered steps, each `done | todo | optional | attention` with a one-line detail, a count and the
   screen that fixes it: documents, floors, mapping, site plan, placement, facades, site features (optional),
   gallery, location, prices, architect's 3D model (optional), publish. The admin page "Setup checklist" is
   the first entry of the project menu; the project overview shows a banner with the count while the
   checklist is incomplete. The IFC step tells the developer what to ask the architect for.
6. **Out of the ADR-0016 open items, E2 is closed by this decision**; E3 (facade column) stays open and is
   now unblocked; AI renders for other kinds (exterior, interior) are not generated here.

## Options considered

### Option A: overlay highlight; neutral roofs with a tint mode; provider interface with Gemini image editing, staff review on the existing media flags; checklist from one endpoint (chosen)

Pros: every piece reuses what exists (media flags, layout sharing, readiness, plan viewer); nothing reaches
buyers unreviewed; the provider is a setting; the checklist is testable on the existing fixtures.
Cons: a new table and an outbound dependency with a per-image cost; a generated image can misread a plan
and needs a careful reviewer; the massing stays schematic until the architect's model arrives.

### Option B: generate the 3D plan view procedurally in three.js from the plan's walls and labels

Pros: no cost per image, deterministic, never invents a room. Cons: needs wall and door detection the
mapping does not have, looks like a diagram, never like the owner's reference image; weeks of work.

### Option C: OpenAI GPT Image as the provider

Pros: comparable quality, one more vendor the owner may already have. Cons: model names changed twice in
2026 and the current family retires late 2026 (third-party reports); same token billing. The interface makes
it a day's work when wanted.

### Option D: self-hosted Flux or SDXL in the heavy worker

Pros: no per-image cost, data never leaves the host. Cons: a GPU box the deployment does not have, model
licences to check, slower; out of scope until volumes justify it.

### Option E: a setup wizard that drives the user step by step instead of a checklist

Pros: beginners cannot get lost. Cons: the steps are long-running (processing, mapping) and interleaved
with waiting; a checklist that always shows the state fits better and keeps the expert screens.

## Trade-off analysis

| Axis | A (chosen) | B procedural | C OpenAI | D self-hosted | E wizard |
|---|---|---|---|---|---|
| Looks like the reference image | yes, reviewed | no | yes | depends on the model | — |
| Cost per image | $0.0336 at 1K (Gemini) | 0 | $0.006 to $0.21 | GPU hours | — |
| Data leaves the host | the plan crop | no | the plan crop | no | — |
| New infrastructure | none | none | none | GPU host | none |
| Risk of invented content | mitigated by review and label | none | same as A | same as A | — |
| Fits long-running steps | — | — | — | — | poorly |

## Consequences

Easier: a buyer sees which apartment is selected; the 3D view reads as a building with facades; a developer
with 25 identical flats gets one reviewed 3D plan view for all of them; a new project manager sees what to
do next and what is missing.

Harder: reviewers must look at every generated image for invented doors, rooms or furniture before approval
(the admin card says so); the per-tenant daily cap and the cost line must be kept honest against the vendor's
pricing page; one more secret file in every environment; the response parser of the provider is defensive
because the vendor documents the SDK accessor, not the raw JSON, so the first real call may need a fix
(the error field will show the shape); reviews must hold two rules: roof materials are never tinted, and
nothing with `is_ai_generated` is published without a review action.

Revisit: a second provider when the owner asks; batch pricing (half price) if volumes grow; generating
exterior views from the facade drawings (ADR-0016 Option D) after the first real renders are judged; a
`buildings.facades` column (ADR-0016 E3, now unblocked); an MCP tool for the checklist so an assistant can
report project state.

**Out of scope here:** AI renders of exteriors or interiors; procedural apartment models; wall and door
detection; the architect's model itself (a file the developer must obtain); a setup wizard.

## Action items

### Phase A: backend

- [x] A1 Migration `0014_unit_renders` (table, indexes, RLS); `UnitRender` in `tenants/models.py`.
- [x] A2 `core/settings.py`: `ai_image_provider`, `ai_image_api_key`, `ai_image_model`,
      `ai_image_endpoint`, `ai_image_daily_limit`, `ai_image_cost_per_image_usd`.
- [x] A3 `renders/provider.py`, `renders/gemini.py` (httpx, fixed host, defensive parse),
      `renders/service.py` (crop with mask, prompt, request, approve, reject, list, daily cap),
      `renders/jobs.py` (session closed around the call), task `renders.generate` on `docs`.
- [x] A4 (writes need the `sales` resource like unit media) `api/admin_renders.py` (`GET/POST /units/{id}/renders`, `POST /renders/{id}/approve|reject`),
      schemas `RenderOut`, `RenderRequest`, `RendersOut`; router registered in `main.py`.
- [x] A5 `geometry/massing.py`: caps as a "roof" primitive, material `extras.role`; tests in
      `test_massing_facades.py`.
      *Found while implementing:* the facade material's base colour was the unit-type colour
      multiplied under the texture; it is white now so drawings keep their own tones and the tint
      comes from the viewer.
- [x] A6 `publishing/setup.py` `setup_status(db, project)` and `GET /projects/{id}/setup`
      (`SetupOut`, `SetupStepOut`).
      *Found while implementing:* the "site" pseudo-building (outdoor units) must stay out of the
      floors, placement and facade steps or every project shows them as not done.
- [x] A7 Tests: `tests/test_unit_renders.py` (stub provider: request → job → review media is private →
      approve publishes → reject deletes; daily cap; provider `none` refused; the crop whites out the
      neighbours), setup steps on the publishing world, roof primitive and material roles.
- [x] A8 `openapi.json` and the api-client typings regenerated.

### Phase B: admin app

- [x] B1 `libs/plan-viewer`: overlay, dimming, label; spec.
- [x] B2 `unit-sales/unit-media.component.ts` (or a sibling `unit-renders.component.ts`): "Generate 3D
      plan render" with cost and daily count, request list with status chips, thumbnail, Approve / Reject,
      the reviewer's checklist in the hint; store methods; api-client methods.
- [x] B3 `pages/setup.page.ts`, route `setup`, first project menu entry, overview banner, guide entry
      `setup` (with the IFC paragraph), guide additions for unit sales (renders) and sheet (selection).
- [x] B4 `libs/viewer-3d`: `tintMode`, role-aware painting.

### Phase C: portal

- [x] C1 Project and unit pages default to neutral with the "Availability colours" toggle; building page
      keeps availability; styles for the toggle.
- [x] C2 Screenshot pass on 2026-10-26 over the building page (A-17 selected on the plan and lit in 3D),
      the project page (neutral 3D with grey roofs, the colour switch), the unit page, the setup checklist
      (10 of 12 on the sample project), the overview banner and the unit page's render card (provider off).
      Fixed on the way: the "not enabled" alert wrapped its inline code as flex items.

### Phase D: deploy and docs

- [x] D1 `compose.yaml` secret `ai_image_api_key` on api and workers, `.env.example` lines,
      `secrets/README.md` row, `init-secrets.sh` placeholder (external key, never random).
- [x] D2 README status and decision list, plan §11.2, §11.3, §12.3, §21 (Gemini facts and sources),
      `frontend/README.md`, `docs/BACKLOG.md` rows, ADR-0016 E2 ticked.

### Phase E: open

- [x] E1 (done 2026-10-26: the owner put a key in place; the first live call returned 400 because
      only `image/jpeg` is accepted as output, fixed in `renders/gemini.py`; the second call returned a
      furnished isometric view of A-17 in 30 s for $0.0336, approved by the owner, published in v12.
      *Found while implementing:* the portal unit page listed the image last, under the plan and the 3D
      block, so the owner did not find it; the `plan_render` item now leads the page, shown whole.)
      First real render on the sample project once the owner provides a Gemini API key (file
      `deploy/compose/secrets/ai_image_api_key`, `UF_AI_IMAGE_PROVIDER=gemini`): verify the response
      parser, judge the quality against the reference image, then review and approve or reject.
- [ ] E2 The architect's IFC export for `permit-1127975` (ArchiCAD: File → Save as → IFC, with zones as
      IfcSpace), uploaded under building A; the portal then shows the model instead of the massing.
- [ ] E3 Second provider (OpenAI) if the owner wants a comparison; batch pricing when volumes grow.
- [x] E4 Joined apartments (owner's item 3, 2026-10-26, "dollhouse only"): `RenderRequest.with_unit_id`,
      `unit_renders.partner_unit_id` (migration `0016`), the crop masks both outlines, the prompt asks for
      one enlarged home with the partition opened, the image belongs to the first unit and its alt text
      names both; "Join with" select on the unit page lists the units of the same floor. Test in
      `test_unit_renders.py`. The inventory keeps two units: viewing and sharing only.
      *Found while using (2026-10-26):* the model kept the partition wall although the prompt asked to
      open it. The crop now cuts a white gap into the shared wall (`renders.service.shared_wall`: the
      longest stretch where the two outlines run along each other; the gap is 40 % of it, 24 to 220 px)
      and the prompt says the gap is an open passage; the model follows the drawing more than the text.
      Outlines that do not touch get no gap. Test `test_joined_crop_cuts_an_opening_into_the_shared_wall`.
- [x] E5 Wall colour (owner's item 5): `units.attributes.wall_colour` (RAL code or hex, 1 to 40
      characters) through the sales rules like `layout`; inventory column "Walls", unit form field, public
      on the unit page with a swatch for hex and the common RAL codes; the render prompt paints the walls
      in it.
- [x] E6 Furniture ruler (owner's item 4): the portal unit page adds pieces (beds, sofa, table, wardrobe,
      desk, bathtub) at true scale, computed from the unit's outline and its largest stated area, and the
      buyer drags them on the plan (viewer move mode; the outline is locked). The chips are an icon with
      the size in cm and toggle one piece each (pressed while placed; a second click removes it); the name
      ("Bed 160×200 cm") is the tooltip (native `title`, so not shown on touch screens) and the label on the
      placed piece. Nothing is stored.
- [x] E7 Plan viewer controls (owner's items 1, 2, 10): + / − / fit / full screen on every plan viewer;
      the selected unit on the building page gets a compact callout (code, status, arrow) that opens the unit page; the
      callout takes the pointer itself and a press on it never pans the plan (fixed 2026-10-26).
