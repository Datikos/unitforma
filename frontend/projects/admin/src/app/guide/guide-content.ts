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
  'imports',
  'sales-setup',
  'publish',
  'members',
  'tokens',
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
      { name: 'New project', does: 'Slug (used in the portal URL) and a display name.' },
      {
        name: 'Start from a building permit',
        does: 'Paste a tas.ge permit address. Preview shows the permit facts and which drawings will be imported; Import creates the project, one building and queues the drawings for Documents.',
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
        does: 'Creates floors from the lowest to the highest level; negative levels are basements (B1), 0 is Ground. Use the permit heights as the hint.',
      },
      {
        name: 'Check registry for new files',
        does: 'Fetches the permit again and imports only drawings that are not here yet. An import shown as stalled (importing for over 20 minutes, its worker lost) is closed as failed by this button and a new one starts.',
      },
      {
        name: 'Archive / Reactivate',
        does: 'Archive hides the project from the list and changes nothing else; refused while the portal is published.',
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
        does: 'Tenant admin only, the slug typed in, refused while published. Removes buildings, units, documents, files and publications; the audit log keeps the record. Other roles see the button and get "not allowed".',
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
        name: 'Sheet thumbnails',
        does: 'Open a page in the mapping editor. Exclude pages that are not plans (cover, legend) so they stop proposing floors.',
      },
      {
        name: 'Upload new revision',
        does: 'A newer drawing of the same document. Processed revisions of mapped documents produce a revision diff.',
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
      { name: 'Floor', does: 'Isolates one level; click a unit to see its code.' },
      { name: 'Regenerate', does: 'Queues a rebuild and waits up to a minute for the worker.' },
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
      'Layout is one short code per plan type (for example L1). Units that share it share their renders in the portal, so set it only when the plans are the same.',
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
        name: 'Buyer-visible fields',
        does: 'Toggle what the portal shows for this unit; the preview is what the portal receives.',
      },
      {
        name: 'Media',
        does: 'Renders and photos with alt text; AI-generated images carry a disclosure.',
      },
      {
        name: 'Layout',
        does: 'The plan-type code shared with identical units (1 to 40 characters). A unit without media of its own shows the public media of the first unit with the same code.',
      },
      {
        name: 'Generate 3D plan render',
        does: 'Sends the plan crop of this unit to an image model and lists the result for review. Approve publishes it as a labelled, generated image (shared with the units of the same layout code); Reject deletes it. Off until the installation has an image provider (ADR-0017).',
      },
    ],
    roles: SALES,
    result: 'Published units show the new values on the next publication.',
    tips: ['Entrance (staircase) is shown to buyers next to the floor; it has no privacy switch.'],
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
    ],
    roles: STRUCTURE,
    result: 'The portal at {slug}.unitforma.com serves the latest snapshot.',
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
        name: 'Connect command',
        does: 'The exact command for Claude Code with the host filled in; Claude.ai custom connectors take the same URL and token as an API key.',
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
