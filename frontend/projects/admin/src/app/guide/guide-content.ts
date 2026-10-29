/**
 * The guide ships with the screens (ADR-0009 Decision 8): one entry per route key set in
 * `app.routes.ts` (`data.guide`). Edited together with the page it describes.
 * Roles are the ones the backend accepts for the page's write calls; the menu does not hide pages.
 */
export interface GuideEntry {
  title: string;
  icon: string;
  purpose: string;
  controls: { name: string; does: string }[];
  roles: string[];
  /** Who or what the result waits for. */
  waits?: string;
  /** Where the result lands. */
  result?: string;
  tips?: string[];
}

export const GUIDE_ORDER = [
  'home',
  'platform-tenants',
  'projects',
  'project-overview',
  'setup',
  'documents',
  'sheet',
  'proposals',
  'proposal',
  'placement',
  'massing',
  'units',
  'inventory',
  'unit-sales',
  'layouts',
  'imports',
  'sales-setup',
  'publish',
  'members',
  'tokens',
  'settings',
  'audit',
] as const;

export type GuideKey = (typeof GUIDE_ORDER)[number];

const ALL = ['tenant_admin', 'project_manager', 'sales', 'architectural_reviewer'];
const STRUCTURE = ['tenant_admin', 'project_manager'];
const MAPPING = ['tenant_admin', 'project_manager', 'architectural_reviewer'];
const SALES = ['tenant_admin', 'project_manager', 'sales'];

export const GUIDE: Record<GuideKey, GuideEntry> = {
  home: {
    title: 'Your workspaces',
    icon: 'lucideHouse',
    purpose:
      'Every developer company you belong to is a workspace. Pick one to work in; the side menu then shows its projects, members and audit log.',
    controls: [
      {
        name: 'Workspace card',
        does: 'Opens the workspace. The role under the name is what you may do there.',
      },
      {
        name: 'Manage tenants',
        does: 'Platform administrators only: create workspaces and invite their first administrator.',
      },
    ],
    roles: ALL,
    tips: [
      'No workspace listed? Ask the workspace administrator for an invitation link; it is tied to your e-mail address.',
    ],
  },
  'platform-tenants': {
    title: 'Tenants (platform)',
    icon: 'lucideLandmark',
    purpose:
      'Create a developer workspace: its slug becomes the portal address {slug}.unitforma.com. The first administrator receives an invitation link.',
    controls: [
      {
        name: 'Create a tenant',
        does: 'Reserves the slug and creates the workspace with EUR as its default currency.',
      },
      {
        name: 'First admin email',
        does: 'Issues an invitation link for that address. Until e-mail delivery exists, copy the link and send it yourself.',
      },
    ],
    roles: ['platform_admin'],
    result: 'The workspace appears in the table; open it from its name.',
  },
  projects: {
    title: 'Projects',
    icon: 'lucideFolderKanban',
    purpose:
      'A project is one development: buildings, floors, units, documents and a published portal page. Create one by hand or start from a public building permit.',
    controls: [
      {
        name: 'New project',
        does: 'Slug (used in the portal URL), a display name, the address line, the currency (the workspace default when empty), the code of the first building (A) and, optionally, the drawings: each file becomes a document under that building and is processed at once.',
      },
      {
        name: 'Set up automatically',
        does: 'On by default. When the drawings are processed, the setup solver accepts the floors read from the level markers, assigns the sheets to their floors, calibrates them from the printed scale, outlines the units the drawing names clearly (confidence 0.9 or more), aligns the floor sheets of each building on the drawing’s grid axes (the bubbles A, B, 1, 2 … at both ends of each axis), picks the site plan, places the building, publishes render documents to the gallery, puts the address on the map and proposes plan types. Everything it did and everything it left for you is listed on the setup checklist.',
      },
      {
        name: 'Approve mapped sheets',
        does: 'Only with the mapping approve right. When every apartment label printed on a sheet is outlined, the sheet is approved and its units become active (not yet published). Off: the units stay drafts for you to approve in the sheet editor.',
      },
      {
        name: 'Publish the first version with defaults',
        does: 'Needs the mapping approve, sales write and publish rights (ADR-0029). When the solver has nothing left processing and the project has no publication yet, the run ends by approving its drafts, confirming its plan types, writing a first description from the project\'s facts, listing every active unit with prices on request and publishing version 1. Later versions are yours: adjust and publish on the Publish page, or press "Publish with defaults" on the setup checklist.',
      },
      {
        name: 'Start from a building permit',
        does: 'Paste a tas.ge permit address. Preview shows the permit facts and which drawings will be imported; Import creates the project, one building and queues the drawings for Documents. With "Set up automatically" the solver runs once the last drawing is processed.',
      },
      { name: 'Search', does: 'Filters the list by name, slug or permit number.' },
      {
        name: 'Show archived',
        does: 'Archived projects are hidden by default; the toggle lists them. Open one to reactivate it.',
      },
    ],
    roles: STRUCTURE,
    waits:
      'A permit import runs in the background; its drawings appear under Documents within about a minute.',
  },
  'project-overview': {
    title: 'Overview & structure',
    icon: 'lucideLayoutDashboard',
    purpose:
      'The project header, its permit (when imported) and the structure: buildings with their floors. Floors are what sheets, units and the 3D model attach to.',
    controls: [
      {
        name: 'Add building',
        does: 'A code (A, B, …) and an optional name. Codes appear in unit codes and in the portal.',
      },
      {
        name: 'Generate floors',
        does: 'Creates floors from the lowest to the highest level; negative levels are basements (B1), 0 is Ground. Use the permit heights as the hint. Levels already there are updated; nothing is deleted.',
      },
      {
        name: 'Delete (floor)',
        does: 'The bin in the floor table removes a floor no unit uses, such as a level read off an outside ground mark. Refused while any unit is on it, removed ones included. Sheets assigned to it become unassigned and the page → floor suggestions are refreshed.',
      },
      {
        name: 'Check registry for new files',
        does: 'Fetches the permit again and imports only drawings that are not here yet. An import shown as stalled (importing for over 20 minutes, its worker lost) is closed as failed by this button and a new one starts. A file the lost import had filed but left "Queued" is queued for processing again by the new import; a sweep every 10 minutes does the same for any file queued or processing for over 15 minutes without a worker, three tries, then it is marked failed with "worker lost".',
      },
      {
        name: 'Archive / Reactivate',
        does: 'Archive hides the project from the list and changes nothing else; a published portal goes offline first and Reactivate does not publish it again.',
      },
      {
        name: 'Delete (building)',
        does: 'Removes an empty building with its floors and 3D models; refused while any unit belongs to it, in any state.',
      },
      {
        name: 'Shown to buyers (building)',
        does: 'Construction status, completion and terms of this building, and the section or elevation sheet whose level markers become the floor picker on the portal. Saved per building; buyers see it after the next publication.',
      },
      {
        name: 'Delete project permanently',
        does: 'Tenant admin only, the slug typed in. A published portal goes offline first, then buildings, units, documents, files and publications are removed; the audit log keeps the record. Other roles see the button and get "not allowed".',
      },
    ],
    roles: STRUCTURE,
    tips: [
      'Floors can be regenerated while no unit is mapped on them. After that, change floors one by one.',
      'To delete a building that has units, delete the project instead: units are never removed one by one.',
    ],
  },
  setup: {
    title: 'Setup checklist',
    icon: 'lucideClipboardCheck',
    purpose:
      'The order of work for a project on one page: each step says whether it is done, what is still missing and which screen completes it. Optional steps are marked; the count at the top is what the portal still lacks.',
    controls: [
      {
        name: 'Steps',
        does: 'Floor plans → floors → mapping → site plan → placement → facades → features → gallery → map position → prices → architect\'s 3D model → publish. "Done" is computed from the data, never ticked by hand.',
      },
      {
        name: 'Open',
        does: 'Jumps to the screen that completes the step; come back here to see the next one.',
      },
      {
        name: 'Set up automatically',
        does: 'The setup solver (ADR-0025) applies the confident proposals after every processed document: floors, sheet floors, calibration (a printed scale, or your calibration of one page for the other pages of its document), unit outlines at 0.85 or more, the floor alignment on the grid axes, the site plan, the placement, the gallery, the map position, proposed plan types. "Approve mapped sheets" needs the mapping approve right. Switching on runs it now; "Run now" runs it once whatever the switch says.',
      },
      {
        name: 'Publish with defaults',
        does: 'One confirmed click (ADR-0029): a run that ends with a live portal. It approves every sheet whose outlines the solver drew, confirms the proposed plan types, writes a first description when there is none, lists every active unit (prices stay as they are) and publishes a new version. Nothing a person set is changed. The same as the third switch at intake, which does it once for the first version.',
      },
      {
        name: 'To do',
        does: 'Under every line that needs you: one sentence saying what to do, and a button that opens the place, the page itself when the line is about one sheet.',
      },
      {
        name: 'Decided for you',
        does: 'Every decision of the last run with its confidence, lowest first; the items marked "Needs you" come first of all and name the screen where you finish them. A step\'s own line says what was done for it. While a run is queued or running the page refreshes every 5 seconds.',
      },
      {
        name: "Architect's 3D model",
        does: 'Optional. Ask the architect for an IFC export (ArchiCAD: File → Save as → IFC, zones as IfcSpace) and upload it under the building as a document; after linking its spaces to the units the portal shows the real building instead of the schematic massing.',
      },
    ],
    roles: STRUCTURE,
    result: 'A project with every required step done publishes without warnings.',
  },
  documents: {
    title: 'Documents',
    icon: 'lucideFileText',
    purpose:
      'Upload what you have: site plans, floor plans, sections, elevations, renders, schedules, models. Each upload becomes a document with revisions; the worker reads pages, guesses the kind and proposes which floor each sheet shows.',
    controls: [
      {
        name: 'Upload files',
        does: 'Several files at once. The kind is guessed from the file name first and from the content after processing; confirm or change it on the card.',
      },
      {
        name: 'Needs a kind',
        does: 'Filters to documents whose kind is still a guess or missing.',
      },
      {
        name: 'Building',
        does: "The building a document is filed under, or project level. With several buildings, file each plan set under its building: a building's floor proposal reads only its own documents, and sheet suggestions prefer its floors. Keep site plans, renders and sheets that show several blocks at project level. Changing it keeps confirmed floor assignments and refreshes the suggestions on the document's sheets a moment later; setting the kind to Floor plans does the same.",
      },
      {
        name: 'Sheet thumbnails',
        does: 'Open a page in the mapping editor. Exclude pages that are not plans (cover, legend) so they stop proposing floors.',
      },
      {
        name: 'Upload new revision',
        does: 'A newer drawing of the same document. Processed revisions of mapped documents produce a revision diff.',
      },
      {
        name: 'Process again',
        does: 'Reads the current revision again: when it is stuck queued or processing, failed, or was processed before an improvement of the drawing reader. Sheets, floor assignments, calibrations and units stay. While a worker still has the revision the button answers "Processing is under way". A stuck revision is also queued again on its own after 15 minutes. Models have no such button: Re-run conversion on the 3D massing page converts them again.',
      },
      {
        name: 'Show in portal gallery',
        does: 'On a render document only. Its pages become the portal gallery and the project cover with the next publication; plans, sections and elevations stay internal.',
      },
      {
        name: 'Delete',
        does: 'Removes the document with its revisions, sheets and files. When units are outlined on it, a second dialog states how many; deleting then removes their outlines and queues a 3D rebuild, the units themselves stay.',
      },
    ],
    roles: MAPPING,
    waits: 'Processing runs in the background; the status chip on the card follows it.',
    result:
      'Processed sheets appear under the document; floor suggestions appear in the sheet editor.',
  },
  sheet: {
    title: 'Sheet mapping',
    icon: 'lucideRuler',
    purpose:
      'Turn one drawing page into units: confirm which floor(s) it shows, calibrate the scale, draw or accept unit boundaries, name and type them, approve.',
    controls: [
      {
        name: 'View / Calibrate / Draw',
        does: 'View pans and zooms. Calibrate: click two points and type the real distance (or accept the scale read from the drawing). Draw: click corners to outline a unit, double-click to close.',
      },
      {
        name: 'Suggested boundaries',
        does: 'Closed outlines the worker found. Accept the right ones; the confidence tells how sure it is.',
      },
      {
        name: 'Read printed areas',
        does: 'Takes the area printed inside each outline as the printed area of the unit.',
      },
      {
        name: 'Approve',
        does: 'Creates permanent unit records from the draft boundaries. Unit identity never changes after this; later revisions are matched against it.',
      },
    ],
    roles: MAPPING,
    waits:
      'Approval is the review step: nothing becomes a unit before it. The unit picked in the list is drawn on top of the sheet with a halo; the others fade until you pick another.',
    result:
      'Units & lineage lists the created units; Inventory can price them; the 3D massing regenerates.',
  },
  proposals: {
    title: 'Revision diffs',
    icon: 'lucideGitCompare',
    purpose:
      'When a new revision of a mapped document is processed, the worker compares its line work with the approved boundaries and proposes relabels, splits, merges, new and missing units.',
    controls: [
      { name: 'Review', does: 'Opens the proposal with the old and the new drawing side by side.' },
    ],
    roles: MAPPING,
    waits: 'Nothing changes until a reviewer accepts or rejects each item.',
  },
  proposal: {
    title: 'Revision diff review',
    icon: 'lucideGitCompare',
    purpose:
      'Decide each proposed change. Accepting a relabel keeps the unit id and changes its code; a split or merge records lineage so prices and leads stay attached to the right units.',
    controls: [
      {
        name: 'Accept / Reject',
        does: 'Per item. Accepted items are applied at once and written to the lineage log.',
      },
      { name: 'Old / New', does: 'The two drawings; the selected item is highlighted on both.' },
    ],
    roles: MAPPING,
    result: 'Units & lineage shows the events; the inventory follows the new codes.',
  },
  placement: {
    title: 'Site placement',
    icon: 'lucideMap',
    purpose:
      'Put each building footprint on the site plan: position, rotation and scale. Placement feeds the portal site view and the 3D massing.',
    controls: [
      { name: 'Site plan', does: 'Pick the document that is the site plan.' },
      {
        name: 'Drag / Two-point align',
        does: 'Drag a footprint, or click two matching points on footprint and site plan to align it.',
      },
      {
        name: 'Confirm',
        does: 'Marks the placement as confirmed; a changed footprint is marked until saved.',
      },
      {
        name: 'Site features',
        does: 'Gardens, roads, parking, amenities and entrances drawn on the site plan. Public features fill the portal site plan and become grass, paving and generic trees in 3D; nothing is drawn that you did not draw.',
      },
      {
        name: 'Facades',
        does: 'Per building side: pick the elevation sheet, mark the drawing area (the facade without its title block), tick Flip when the sheet shows the side from the other direction. Saving queues a 3D rebuild that wraps the drawing onto that side.',
      },
    ],
    roles: STRUCTURE,
    result:
      'The portal site plan and the 3D view follow the next massing build; a facade without a sheet keeps the availability colour.',
  },
  massing: {
    title: '3D massing',
    icon: 'lucideBox',
    purpose:
      'A schematic 3D model built from the approved floor outlines and the floor heights. Buyers see it on the portal when their device can load it.',
    controls: [
      {
        name: 'Floor',
        does: 'Isolates one level; click a unit to see its code. On the schematic model the other floors fade; on the IFC model the building is cut open 1.2 m above that floor, cut walls show dark as on a plan, its units show as tinted glass and the camera looks down into it. "All floors" shows the whole building again.',
      },
      { name: 'Regenerate', does: 'Queues a rebuild and waits up to a minute for the worker.' },
      {
        name: 'Show IFC model',
        does: "Shows the architect's model with each space tinted like its status chip: green confirmed, amber suggested, red unmatched, grey not a unit. Click a space to select its row.",
      },
    ],
    roles: STRUCTURE,
    tips: [
      '"Units skipped (sheet not calibrated)" means a sheet still needs a scale; "unplaced" means a building has no site placement yet.',
    ],
  },
  units: {
    title: 'Units & lineage',
    icon: 'lucideLayers',
    purpose:
      'Every unit record with its three independent states: lifecycle (draft, active, removed), verification and publication. The lineage log is the history of identities: created, relabelled, split, merged, removed.',
    controls: [{ name: 'Filters', does: 'Narrow by building, type or any of the three states.' }],
    roles: ALL,
    tips: [
      'Units are never deleted or re-keyed; a wrong unit is removed through a revision diff or marked removed.',
    ],
  },
  inventory: {
    title: 'Inventory & prices',
    icon: 'lucideTable',
    purpose:
      'The sales grid: availability, prices, terms and public fields per unit, editable in place with conflict protection. Column sets show the commercial, the public or the internal view.',
    controls: [
      {
        name: 'Cells',
        does: 'Edit in place; Enter saves. A conflict card appears when someone else changed the row first.',
      },
      { name: 'Bulk edit', does: 'Select rows, choose what to set, preview the count, apply.' },
      {
        name: 'Make public / Link only / Withdraw',
        does: 'Publication per unit. Public units appear in the portal; link-only units open only by direct link.',
      },
      { name: 'Export', does: 'XLSX or CSV of the internal or the public columns.' },
    ],
    roles: SALES,
    tips: [
      'An empty price means "on request" on the portal; never type 0.',
      'Entrance (staircase) is public like the floor: buyers filter by it once they pick a building.',
      'Layout picks a code from the Layouts registry (for example L1). Units linked to one layout show its media in the portal after their own, so link only units with the same plan.',
    ],
  },
  'unit-sales': {
    title: 'Unit: pricing & terms',
    icon: 'lucideCoins',
    purpose:
      'Everything commercial about one unit: price, payment plan, promotions, rooms, description, which fields buyers see, media and the change history.',
    controls: [
      {
        name: 'Save',
        does: 'Saves the changed fields with a version check; a conflict shows both values.',
      },
      {
        name: 'On the plan',
        does: 'The floor plan around the unit with every outline coloured by availability (green available, amber reserved, red sold, grey not for sale); a click on a neighbour opens it, "Open the sheet" goes to the drawing.',
      },
      {
        name: 'Same floor / layout',
        does: 'Links to the other units of the floor as availability chips, and to the layout this unit belongs to with the other units linked to it.',
      },
      {
        name: 'Price per m²',
        does: 'Computed live from the typed price and the pricing area (green when the area is verified, amber when not); the saved figure is in the header.',
      },
      {
        name: 'Buyer-visible fields',
        does: 'Toggle what the portal shows for this unit; the preview is what the portal receives.',
      },
      {
        name: 'Media',
        does: 'Renders and photos with alt text; AI-generated images carry a disclosure.',
      },
      {
        name: 'Layout',
        does: "The plan type from the Layouts registry, picked from the list (a code not in the registry is refused). The portal shows the layout's public media after the unit's own; clearing the field unlinks the unit.",
      },
      {
        name: 'Walls (RAL or hex)',
        does: 'The wall finish buyers read on the unit page, as a RAL code or a hex colour; the generated 3D plan render paints the walls in it.',
      },
      {
        name: 'Join with',
        does: 'Picks a neighbour on the same floor: the 3D plan render then shows both apartments as one enlarged home: the crop sent to the model has a gap cut into the shared wall, rendered as an open passage. For viewing and sharing only; the inventory keeps two units.',
      },
      {
        name: 'Generate 3D plan render',
        does: 'Sends the plan crop of this unit to an image model and lists the result for review. Approve publishes it as a labelled, generated image of this unit only; a render for every unit of a plan type is made once on the Layouts page. Reject deletes it. Off until the installation has an image provider (ADR-0017).',
      },
    ],
    roles: SALES,
    result: 'Published units show the new values on the next publication.',
    tips: ['Entrance (staircase) is shown to buyers next to the floor; it has no privacy switch.'],
  },
  layouts: {
    title: 'Layouts & renders',
    icon: 'lucideLayoutGrid',
    purpose:
      'The registry of plan types of the project (ADR-0022): one card per layout with its code, name, the units linked to it and the media every one of them shows. Upload a render or photo once per plan type, or generate a 3D plan render once and review it here.',
    controls: [
      {
        name: 'New layout',
        does: 'A code (1 to 40 characters, unique in the project without case) and an optional name such as "Two rooms, corner".',
      },
      {
        name: 'Proposed',
        does: 'A plan type the setup solver found: apartments whose outlines coincide (IoU 0.95 or more); a mirrored flat gets its own code with an "m". It owns no media and buyers never see it until you press Confirm; delete it if the grouping is wrong: the units keep everything of their own and the solver never proposes that grouping again.',
      },
      {
        name: 'Units',
        does: 'The linked units as availability chips; each opens its sales page. Link or unlink a unit on its sales page or in the inventory grid (Layout column).',
      },
      {
        name: 'Media',
        does: "Renders, photos and documents owned by the layout: public ones reach every linked unit on the portal after the unit's own media, with the layout code shown to buyers.",
      },
      {
        name: 'Generate 3D plan render',
        does: "Crops the plan of one linked unit (the first with an outline, or the one you pick) and asks the image model once for the layout; approve publishes it to every linked unit. Counts against the tenant's daily render cap.",
      },
      {
        name: 'Rename',
        does: 'Changes the code or the name; every linked unit follows the new code.',
      },
      {
        name: 'Delete',
        does: "Refused while units are linked; the dialog offers to unlink them. The layout's media files are removed at once.",
      },
    ],
    roles: SALES,
    result: 'Published units show the layout media on the next publication.',
    tips: [
      'A render made on a unit page belongs to that unit only (for example two apartments joined); make the shared one here.',
    ],
  },
  imports: {
    title: 'Import prices',
    icon: 'lucideFileSpreadsheet',
    purpose:
      'Load prices and terms from a spreadsheet in three steps: upload, map the columns, dry run, then apply.',
    controls: [
      {
        name: 'Dry run',
        does: 'Matches rows to units by code and lists what would change and what cannot be matched. Nothing is written.',
      },
      { name: 'Apply', does: 'Writes the dry-run result. Discard throws the batch away.' },
    ],
    roles: SALES,
    waits: 'Apply is explicit; a dry run never changes a unit.',
  },
  'sales-setup': {
    title: 'Plans & promotions',
    icon: 'lucideHandCoins',
    purpose:
      'Project defaults for the sales grid: which area a price per m² refers to, which fields are public by default, payment plans with milestones and promotions.',
    controls: [
      {
        name: 'Payment plan',
        does: 'Named milestones with a percent and a due description; assign plans per unit in the inventory.',
      },
      {
        name: 'Promotion',
        does: 'A discount, gift or financing offer with its validity; assign per unit.',
      },
    ],
    roles: SALES,
  },
  publish: {
    title: 'Publish',
    icon: 'lucideRocket',
    purpose:
      'Check readiness, preview the portal, publish an immutable snapshot, set the portal text and the branding.',
    controls: [
      { name: 'Readiness', does: 'Blocking items must be fixed; warnings may be published with.' },
      { name: 'Preview', does: 'A signed link that shows the unpublished state to you only.' },
      {
        name: 'Publish / Unpublish',
        does: 'Publish creates a numbered snapshot buyers see; unpublish takes the project off the portal until the next publish.',
      },
      {
        name: 'Branding',
        does: 'Display name, tagline, colours, contact and legal text of the portal.',
      },
      {
        name: 'Price note / Terms',
        does: 'The price note is printed next to every price (for example the settlement currency rule); the terms are the default for buildings without their own.',
      },
      {
        name: 'Location',
        does: 'Latitude and longitude of the site in decimal degrees; the OpenStreetMap link searches the typed address. The portal shows a map around the position once published.',
      },
      {
        name: 'Currency',
        does: 'The ISO 4217 code new prices get (EUR, USD, GEL). Prices already entered on units keep their own currency.',
      },
    ],
    roles: STRUCTURE,
    result:
      'The portal at {slug}.unitforma.com serves the latest snapshot. Availability and prices of published units change there at once (ADR-0018); outlines, plans, renders, texts and listing wait for the next version.',
  },
  members: {
    title: 'Members',
    icon: 'lucideUsers',
    purpose:
      'Who works in this workspace and with which role. Invitations are tied to an e-mail address and may be restricted to selected projects.',
    controls: [
      {
        name: 'Invite',
        does: 'Creates an invitation link. Tenant admin: everything. Project manager: structure, documents, publishing. Sales: inventory and prices. Architectural reviewer: mapping and revision diffs.',
      },
      { name: 'Role select', does: 'Changes a member’s role at once.' },
      {
        name: 'Suspend',
        does: 'Keeps the record but blocks sign-in to this workspace; Activate reverses it.',
      },
    ],
    roles: ['tenant_admin'],
  },
  tokens: {
    title: 'API tokens',
    icon: 'lucideKeyRound',
    purpose:
      'Personal tokens that let an AI assistant (Claude Code, Claude.ai) or a script work in this workspace as you, through the MCP server at /mcp. A token never does more than your role allows; a read token changes nothing.',
    controls: [
      {
        name: 'Create token',
        does: 'Name, scope (read or write) and expiry (90 days by default, one year at most). The secret is shown once; copy it into your assistant right away.',
      },
      {
        name: 'Connect an assistant',
        does: 'Always on top: the MCP server URL, the Claude Code command, a .mcp.json snippet, the Claude.ai connector settings and a curl test, each with Copy. They carry a placeholder until you create a token, then its secret.',
      },
      {
        name: 'Revoke',
        does: 'Stops the token on its next call. Tenant admins see and revoke every token of the workspace; other members only their own.',
      },
    ],
    roles: ALL,
    tips: [
      'Tokens are bearer secrets, not OAuth sign-ins: anyone holding the secret acts as you until it expires or is revoked.',
      'Every change made through a token lands in the audit log with the token prefix as its request id.',
      'The assistant can find units by the codes you type ("A 21" finds A21 and A-21), list documents, request a generated plan render, confirm a proposed plan type and run the setup solver. Deleting, uploading, drawing outlines, approving renders and publishing stay in the admin app.',
      'A token acts through your membership in this workspace. A platform admin who is not a member sees the reason instead of the Create button: get invited as a member first; the token then carries that role, never platform rights.',
    ],
  },
  settings: {
    title: 'Settings',
    icon: 'lucideSettings',
    purpose:
      'Workspace-wide settings. Today one: the base prompt every generated 3D plan render starts from (ADR-0023). It applies to every project of the workspace from the next request on; a render already queued keeps the text it was made with.',
    controls: [
      {
        name: 'Base prompt',
        does: 'The text sent to the image model before the plan crop. Pre-filled with the built-in default until you save your own; up to 4000 characters. The joined-apartment sentence, the wall colour of the unit and the note typed on the render panel are added after it automatically: do not repeat them.',
      },
      { name: 'Save', does: 'Stores the text for the workspace and writes an audit row.' },
      {
        name: 'Reset to default',
        does: 'Removes the workspace text; renders use the built-in default again.',
      },
    ],
    roles: ['tenant_admin'],
    result:
      'The next "Generate" on a unit or a layout composes its prompt from this text; the audit log shows who changed it.',
    tips: [
      'Keep the constraints of the default: "keep the exact wall layout, room proportions, door and window positions as drawn; do not add or remove rooms" and "no text, no labels, no dimension lines, no people". Dropping them is what makes renders unusable.',
      'Change one thing at a time (floor material, camera angle, light) and judge it on one unit: each try costs one render.',
    ],
  },
  audit: {
    title: 'Audit log',
    icon: 'lucideScrollText',
    purpose:
      'Every change made through the API: who (role), what entity, which action and the values after the change.',
    controls: [
      { name: 'Filters', does: 'By entity type and action; Load more pages back in time.' },
    ],
    roles: ['tenant_admin', 'project_manager'],
  },
};

/** The flow of a project, drawn on the guide page. */
export const PROJECT_FLOW: { key: GuideKey; label: string; icon: string }[] = [
  { key: 'project-overview', label: 'Structure', icon: 'lucideLayoutDashboard' },
  { key: 'documents', label: 'Documents', icon: 'lucideFileText' },
  { key: 'sheet', label: 'Mapping', icon: 'lucideRuler' },
  { key: 'units', label: 'Units', icon: 'lucideLayers' },
  { key: 'inventory', label: 'Prices', icon: 'lucideTable' },
  { key: 'publish', label: 'Publish', icon: 'lucideRocket' },
];

export function roleLabel(role: string): string {
  return (
    {
      tenant_admin: 'Tenant admin',
      project_manager: 'Project manager',
      sales: 'Sales',
      architectural_reviewer: 'Architectural reviewer',
      platform_admin: 'Platform admin',
    }[role] ?? role
  );
}
