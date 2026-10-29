import { EDGE_SHADER, FULL_TIER_MIN_MEMORY_GB, renderTier } from './architectural-look';

describe('renderTier (ADR-0033 Decision 4)', () => {
  const desktop = { webgl2: true, saveData: false, deviceMemoryGb: 8, viewportWidth: 1440 };

  it('gives a desktop with WebGL2 occlusion and edges', () => {
    expect(renderTier(desktop)).toBe('full');
  });

  it('gives a browser that hides its memory the full tier too (Safari, Firefox)', () => {
    expect(renderTier({ ...desktop, deviceMemoryGb: null })).toBe('full');
  });

  it('keeps a data-saver phone on edges only', () => {
    expect(renderTier({ ...desktop, saveData: true, viewportWidth: 390 })).toBe('edges');
  });

  it('keeps a device under the memory line on edges only', () => {
    expect(renderTier({ ...desktop, deviceMemoryGb: FULL_TIER_MIN_MEMORY_GB - 2 })).toBe('edges');
  });

  it('keeps a narrow viewport on edges only, whatever the memory', () => {
    expect(renderTier({ ...desktop, viewportWidth: 600 })).toBe('edges');
  });

  it('draws plainly without WebGL2', () => {
    expect(renderTier({ ...desktop, webgl2: false })).toBe('plain');
  });
});

describe('the edge shader', () => {
  it('declares every uniform it samples or reads', () => {
    for (const name of Object.keys(EDGE_SHADER.uniforms)) {
      expect(EDGE_SHADER.fragmentShader).toContain(`uniform`);
      expect(EDGE_SHADER.fragmentShader).toMatch(new RegExp(`uniform \\w+ ${name};`));
    }
  });
});
