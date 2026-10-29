/** "How to use this portal": content next to the routes, edited with the screens (ADR-0009 Decision 8). */
export interface PortalGuideSection {
  title: string;
  icon: string;
  text: string;
  points?: string[];
}

export const PORTAL_GUIDE: PortalGuideSection[] = [
  {
    title: 'Finding a unit',
    icon: 'lucideLayoutGrid',
    text: 'Start from the project page, pick a building and a floor, or open Units and filter. Every unit has a code such as A-3-12: building, floor, number.',
    points: [
      'The filter state is in the address bar, so a filtered list can be shared as a link.',
      'Units with price on request are left out of price filters.',
      'Switch the list between cards and a table (building, floor, entrance, unit, area, price); the choice is remembered in this browser.',
      'Pick a building first to filter by entrance: entrance numbers repeat from building to building.',
    ],
  },
  {
    title: 'Plan types',
    icon: 'lucideLayoutGrid',
    text: 'When the developer groups the units by plan type, the project page shows the plan types and "Plan types" lists each one with its render, the rooms, the area range, the lowest price and how many units are still available. The count is live: a sale shows at once.',
    points: [
      'Every unit of a plan type has the same layout; the finish, the floor and the view differ per unit, so the renders are illustrative.',
      '"See the units" opens the units list filtered by that plan type; the Plan type filter on the list does the same.',
      'A unit page names its plan type under the renders and links to the other units of it.',
      'When a unit has several 3D views of its plan, page through them with the arrows, the dots under the picture, the arrow keys or a swipe; "1 / 2" says which one you see.',
    ],
  },
  {
    title: 'What the colours mean',
    icon: 'lucideTag',
    text: 'The same colours appear on plans, in the 3D view and on every card.',
    points: [
      'Green: available.',
      'Amber: reserved by another buyer; it may become available again.',
      'Red: sold.',
      'Grey: not for sale at the moment.',
    ],
  },
  {
    title: 'Plans, 3D and "indicative"',
    icon: 'lucideBox',
    text: 'Floor plans and the 3D building come from the developer’s drawings. Tap a unit on a plan or on the 3D building to open it; on a desktop the unit under the mouse is outlined in its status colour before you click. The + and − buttons zoom a plan, ⤢ fits it again and ⛶ shows it full screen; the selected unit gets a small label right on the plan with its code and status; tap the label to open the unit. Under the plan the legend counts the units of the floor by status, and the list groups them by type (apartments, parking, …) in code order; each tile carries the status colour and icon, and a tap opens the unit.',
    points: [
      'Where the developer published a facade drawing, the building page shows it with one band per floor: tap a band to open that floor. Phones start there; desktops start in 3D.',
      'When the 3D building comes from the architect’s model, choosing a floor cuts the building open just above it: you look down into that floor’s rooms, the cut walls drawn dark as on a plan, and its flats are tinted in their status colours. The building page opens on the whole building, roof included; "Whole building" above the 3D view shows it whole again.',
      'A building card shows its construction status (planned, under construction, completed) and the completion the developer stated.',
      '"Indicative" means the plan or the area has not yet been verified against the final drawings; the figures may change.',
      'Areas are listed by type (for example net, gross, terrace); the definition is shown when you hover a row.',
      '"Design this apartment" under the unit plan opens the planner in a new window: only that apartment on the left (the neighbours are covered), the tools on the right. Pick a room (bedroom, living, kitchen, bathroom, hall, balcony), tap a piece in the catalogue to put it on the plan at its real size (the size is in cm; add the same piece as often as you like), drag it where you want it. "On the plan" lists what you placed: tap a row to select the piece, use its buttons to turn it by 90°, flip it or remove it (on a keyboard: R, F, Delete), "Clear all" starts over. "Empty the apartment" fades what the architect drew so your pieces stand out; "Walls" tries a colour on the plan (the developer\'s stated colour is shown next to it). The arrangement is kept in this browser for this unit (the line at the bottom says so, and the unit page shows the count) and nothing is sent to the developer.',
      'Share copies a link that opens this unit with your arrangement, for example to send to your partner on WhatsApp. Whoever opens it sees your pieces with a note; their own saved arrangement stays untouched until they change something, and the first change makes the shared one theirs.',
      "Furniture needs a stated area: the scale of the plan comes from the unit's area, so a unit without one shows the plan alone and says why.",
    ],
  },
  {
    title: 'Prices and terms',
    icon: 'lucideCoins',
    text: 'Prices are shown in the project’s currency; the price per square metre refers to the area type named next to it. Payment plans and promotions apply as described on the unit.',
    points: [
      '"Price on request" means the developer has not published a price for that unit; ask the sales team.',
    ],
  },
  {
    title: 'Saving units',
    icon: 'lucideHeart',
    text: 'Save keeps a unit in this browser so you can compare later. Saved units do not follow you to another device yet; a buyer account arrives in a later release.',
  },
  {
    title: 'Asking about a unit',
    icon: 'lucideMail',
    text: '"Ask about this unit" opens an e-mail to the developer’s sales team with the project and the unit code in the subject.',
  },
];
