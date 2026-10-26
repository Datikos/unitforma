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
    text: 'Floor plans and the 3D building come from the developer’s drawings. Tap a unit on a plan or on the 3D building to open it. The + and − buttons zoom a plan, ⤢ fits it again and ⛶ shows it full screen; the selected unit gets an Open button right on the plan.',
    points: [
      'Where the developer published a facade drawing, the building page shows it with one band per floor: tap a band to open that floor. Phones start there; desktops start in 3D.',
      'A building card shows its construction status (planned, under construction, completed) and the completion the developer stated.',
      '"Indicative" means the plan or the area has not yet been verified against the final drawings; the figures may change.',
      'Areas are listed by type (for example net, gross, terrace); the definition is shown when you hover a row.',
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
