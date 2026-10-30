import { siteBadge } from './site-view.model';

const IFC = "Model from the architect's IFC export";
const building = (code: string, placed: boolean, units = 1) => ({
  code,
  name: `Block ${code}`,
  model: placed
    ? {
        url: 'x',
        bytes: 1,
        kind: 'ifc',
        disclaimer: IFC,
        built_at: null,
        site_matrix: Array(16).fill(0),
      }
    : null,
  floors: [{ level: 0, units: Array.from({ length: units }, (_, i) => ({ id: `${code}${i}` })) }],
});

describe('the site view disclaimer (ADR-0037 Decision 3)', () => {
  it('says schematic while no architect model sits on the site', () => {
    expect(siteBadge([building('A', false)] as never)).toContain('Schematic model');
  });

  it("is the architect's when every building with units is placed", () => {
    expect(siteBadge([building('A', true), building('S', false, 0)] as never)).toBe(IFC);
  });

  it('names the placed buildings when the others are schematic', () => {
    expect(siteBadge([building('A', true), building('B', false)] as never)).toBe(
      "Block A: the architect's model; the others are schematic, generated from floor plans",
    );
  });
});
