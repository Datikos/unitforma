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

# --- floors
FLOORS_CONFIDENCE_WITH_ROOF = 0.9
FLOORS_CONFIDENCE_NO_ROOF = 0.8
# split-level blocks whose merged storeys are lower than this are not one storey list
FLOOR_MIN_HEIGHT_M = 2.2

# --- calibration from the single printed scale of a sheet
CALIBRATION_CONFIDENCE = 0.85

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

# --- classify: a kind the vision model names for an unclassified drawing page
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
}
