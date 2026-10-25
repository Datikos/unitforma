import { parsePages } from './page-ranges';

describe('parsePages', () => {
  it('expands ranges and lists, sorted and unique', () => {
    expect(parsePages('12-14, 7 7;3')).toEqual([3, 7, 12, 13, 14]);
    expect(parsePages('9-7')).toEqual([7, 8, 9]);
  });
  it('ignores junk and caps the size', () => {
    expect(parsePages('a, -3, 0, 2x')).toEqual([]);
    expect(parsePages(undefined)).toEqual([]);
    expect(parsePages('1-99999').length).toBe(2000);
  });
});
