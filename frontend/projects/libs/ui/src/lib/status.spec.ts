import { UF_ICONS } from './icons';
import { STATUS_TABLES, StatusDomain, humanise, statusChipHtml, statusOf } from './status';

describe('status vocabulary', () => {
  it('every domain value maps to a label, a tone and an icon that exists in UF_ICONS', () => {
    for (const [domain, table] of Object.entries(STATUS_TABLES)) {
      for (const [value, view] of Object.entries(table)) {
        expect(view.label, `${domain}.${value}`).not.toBe('');
        expect(UF_ICONS[view.icon], `${domain}.${value} icon ${view.icon}`).toBeDefined();
        expect(['good', 'warning', 'bad', 'info', 'neutral', 'pending']).toContain(view.tone);
      }
    }
  });

  it('an unknown value renders neutral with the humanised raw text and never throws', () => {
    const s = statusOf('availability', 'on_hold');
    expect(s).toEqual({ tone: 'neutral', label: 'On hold', icon: 'lucideCircleHelp' });
    expect(statusOf('availability', null).label).toBe('Unknown');
    expect(() => statusOf('nope' as StatusDomain, 'x')).toThrow();
  });

  it('availability keeps the colours the portal and the grid rely on', () => {
    expect(statusOf('availability', 'available').tone).toBe('good');
    expect(statusOf('availability', 'reserved').tone).toBe('warning');
    expect(statusOf('availability', 'sold').tone).toBe('bad');
    expect(statusOf('availability', 'withdrawn').label).toBe('Not for sale');
  });

  it('the cell renderer emits the chip classes, the icon svg and an escaped label', () => {
    const html = statusChipHtml('readiness', 'error');
    expect(html).toContain('uf-chip uf-tone-bad');
    expect(html).toContain('<svg');
    expect(html).toContain('Blocking');
    expect(statusChipHtml('readiness', null)).toBe('');
  });

  it('humanise turns snake_case into a sentence', () => {
    expect(humanise('in_review')).toBe('In review');
    expect(humanise('')).toBe('');
  });
});
