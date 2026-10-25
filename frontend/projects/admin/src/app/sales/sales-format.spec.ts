import { formatPrice, parsePriceInput } from './sales-format';

describe('sales price helpers (plan §6.2)', () => {
  it('formats with an explicit currency and keeps empty prices empty', () => {
    expect(formatPrice('245000', 'EUR')).toBe('EUR 245 000.00');
    expect(formatPrice('1234.5', 'GEL')).toBe('GEL 1 234.50');
    expect(formatPrice(null, 'EUR')).toBeNull();
    expect(formatPrice('', 'EUR')).toBeNull();
  });

  it('parses user input to a two-decimal string, empty to null, garbage to undefined', () => {
    expect(parsePriceInput('245 000')).toBe('245000');
    expect(parsePriceInput('245,000.50')).toBe('245000.50');
    expect(parsePriceInput('1234,5')).toBe('1234.5');
    expect(parsePriceInput('')).toBeNull();
    expect(parsePriceInput(null)).toBeNull();
    expect(parsePriceInput('12a')).toBeUndefined();
    expect(parsePriceInput('-5')).toBeUndefined();
    expect(parsePriceInput('1.234')).toBeUndefined();
  });
});
