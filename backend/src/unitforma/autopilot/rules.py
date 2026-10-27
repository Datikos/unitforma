"""The solver's thresholds in one place (ADR-0025 Decision 5 and Consequences). A number here
changes only with a fixture that shows why; the ADR records the reasons.

Confidence figures are what the run summary shows next to a decision; ``needs_you`` marks what the
solver left for a person. The steps and screens are those of the setup checklist (ADR-0017)."""

from __future__ import annotations

# --- outlines: a candidate below this is a proposal for the sheet editor, never a unit. Typed
# fills and loops score 0.9 or more; a numbered fill (a zone with a number and its printed area)
# scores 0.85 and was right 30 times out of 30 on the storage floor of permit 1127975 (2026-10-27);
# grown faces (0.7) traded balcony slivers on the pilot set; a bare number (0.65) stays a proposal.
OUTLINE_MIN_CONFIDENCE = 0.85
# a candidate that overlaps a boundary already drawn by this much is that unit, not a new one
OUTLINE_EXISTING_OVERLAP = 0.3
# a label printed twice on this many sheets, and on this share of the sheets with candidates, is a
# room number or an axis mark (0–7 and "M2" on every plan of permit 1127975, D4), not a unit label
LABEL_SET_WIDE_MIN_SHEETS = 2
LABEL_SET_WIDE_SHARE = 0.5

# --- floors
FLOORS_CONFIDENCE_WITH_ROOF = 0.9
FLOORS_CONFIDENCE_NO_ROOF = 0.8
# split-level blocks whose merged storeys are lower than this are not one storey list
FLOOR_MIN_HEIGHT_M = 2.2

# --- calibration from the single printed scale of a sheet
CALIBRATION_CONFIDENCE = 0.85
# a person's calibration given to the sibling pages of the document (ADR-0029 Decision 3)
CALIBRATION_SIBLING_CONFIDENCE = 0.8
CALIBRATION_PAGE_SIZE_TOLERANCE_PT = 0.5

# --- publish with defaults (ADR-0029 Decision 1): the end state is a live portal
DEFAULTS_APPROVE_CONFIDENCE = 0.7  # drafts approved by rule, whatever the coverage
DEFAULTS_LAYOUTS_CONFIDENCE = 0.8
DEFAULTS_DESCRIPTION_CONFIDENCE = 0.6  # facts the project knows, in a sentence a person replaces
DEFAULTS_PUBLISH_CONFIDENCE = 0.9

# --- sheet → floor
SHEET_FLOOR_SINGLE = 0.9
SHEET_FLOOR_REGIONS = 0.85

# --- site plan, gallery, map
SITE_PLAN_CONFIDENCE = 0.9
GALLERY_CONFIDENCE = 0.9
GEOCODE_CONFIDENCE = 0.7
# several answers within this radius are one address (entrances 19/4 and 19/5 of one street number)
GEOCODE_AGREE_M = 150.0
GEOCODE_PAUSE_S = 1.1  # Nominatim: at most one request per second

# --- placement: the footprint against a closed face of the site plan (IoU after the best rotation)
PLACEMENT_AREA_TOLERANCE = 0.25  # faces within ±25 % of the footprint area are tried
PLACEMENT_CONFIRM_IOU = 0.9
PLACEMENT_DRAFT_IOU = 0.8
PLACEMENT_COARSE_STEP_DEG = 3.0
PLACEMENT_FINE_STEP_DEG = 0.5

# --- facades: the drawn width of an elevation against the side lengths of the footprint rectangle
FACADE_WIDTH_TOLERANCE = 0.05
FACADE_CONFIDENCE = 0.6

# --- layouts: two apartments are one plan type when their outlines coincide this well after the
# best of four orientations (and, for mirrors, the reflection)
LAYOUT_MIN_IOU = 0.95
LAYOUT_AREA_TOLERANCE = 0.08
LAYOUT_MIN_MEMBERS = 2

# --- classify: on the host, a set with this many floor-plan pages is a plan set (ADR-0008 reads
# "half the pages"; a permit's plan set carries sections and details, 6 plan pages in 51)
HOST_KIND_MIN_PLAN_PAGES = 2
HOST_KIND_CONFIDENCE = 0.85
# a kind the vision model names for an unclassified drawing page
CLASSIFY_CONFIDENCE = 0.8
CLASSIFY_KINDS = ("floor_plan", "site_plan", "section", "elevation", "render", "schedule")
CLASSIFY_PROMPT = (
    "This is one page of an architectural drawing set for a residential development. Answer "
    "with exactly one word from this list and nothing else: floor_plan (a plan of one or more "
    "storeys with rooms or apartments), site_plan (the general plan of the plot with buildings, "
    "roads and parking seen from above), section (a vertical cut through the building), "
    "elevation (a facade seen from the side), render (a photographic 3D visualisation), "
    "schedule (a table of areas or rooms), other."
)
CLASSIFY_MAX_EDGE_PX = 1024
# a page leaves the host only when it is a drawing: enough line work and either little text or many
# times more line work than text (a permit decision or an area schedule with table rules has lines
# too, and names people, ADR-0007). A real elevation sheet: 64 444 vectors, 4 676 characters (D2).
CLASSIFY_MIN_VECTORS = 50
CLASSIFY_MAX_TEXT_CHARS = 800
CLASSIFY_MIN_VECTORS_PER_CHAR = 2.0

# what a person does about a "needs you" line of each step (ADR-0029 Decision 5): one imperative
# sentence; a pass gives a more specific one when it knows more
TODO_OF_STEP = {
    "documents": "Upload the drawings on the Documents page, then run again",
    "classify": "Set the kind of the document on the Documents page (the kind menu on its row)",
    "floors": "On the overview: accept the floor proposal, or type the floors of the building",
    "calibration": "Open the page and set two points on a known distance (a dimension line)",
    "sheet_floors": "Open the page and pick its floor at the top of the sheet editor",
    "mapping": "Open the sheet, accept the listed candidates or draw the units, then approve it",
    "site_plan": "Choose the site plan under Site placement",
    "placement": "On Site placement, drag the footprint onto the site plan and confirm",
    "facades": "On Site placement, pick the facade drawing of each side",
    "gallery": "Mark a render document public on the Documents page",
    "location": "Type latitude and longitude on the Publish page, or fix the address and run again",
    "layouts": "Confirm or delete the plan type on Layouts & renders",
    "defaults": "Fix the item named above, then press Publish with defaults again",
}

# the screen of the setup checklist that completes each step (keys of SetupPage.SCREEN)
LINK_OF_STEP = {
    "documents": "documents",
    "classify": "documents",
    "floors": "overview",
    "calibration": "documents",
    "sheet_floors": "documents",
    "mapping": "documents",
    "site_plan": "placement",
    "placement": "placement",
    "facades": "placement",
    "gallery": "documents",
    "location": "publish",
    "layouts": "layouts",
    "defaults": "publish",
}
