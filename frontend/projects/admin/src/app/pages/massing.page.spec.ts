import { IfcSpaceLinkOut } from 'api-client';
import { linkColours, spaceKey } from './massing.page';

const link = (status: string, gid: string, unitId: string | null = null) =>
  ({ status, ifc_global_id: gid, unit_id: unitId }) as IfcSpaceLinkOut;

describe('IFC space tint on the admin 3D page (ADR-0036 #D1)', () => {
  it('keys a confirmed space by its unit and any other by its GlobalId', () => {
    expect(spaceKey(link('confirmed', 'g1', 'u1'))).toBe('u1');
    expect(spaceKey(link('suggested', 'g2', 'u2'))).toBe('space:g2');
    expect(spaceKey(link('confirmed', 'g3'))).toBe('space:g3');
  });

  it('gives every status the hue of its chip', () => {
    expect(
      linkColours([
        link('confirmed', 'g1', 'u1'),
        link('suggested', 'g2', 'u2'),
        link('unmatched', 'g3'),
        link('rejected', 'g4'),
      ]),
    ).toEqual({
      u1: '#34d399',
      'space:g2': '#fbbf24',
      'space:g3': '#f87171',
      'space:g4': '#9ca3af',
    });
  });

  it('leaves a space of an unknown status in the model colour', () => {
    expect(linkColours([link('later', 'g5')])).toEqual({});
  });
});
