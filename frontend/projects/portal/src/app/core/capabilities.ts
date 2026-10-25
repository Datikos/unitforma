/**
 * Capability detection for the 3D fallback ladder (plan §7.3): 3D needs WebGL2; phones and
 * data-saver connections start in 2D ("lite default") and can switch to 3D themselves.
 */
export interface Capabilities {
  webgl2: boolean;
  prefer3d: boolean;
}

export function detectCapabilities(): Capabilities {
  let webgl2 = false;
  try {
    const c = document.createElement('canvas');
    webgl2 = !!c.getContext('webgl2');
  } catch {
    webgl2 = false;
  }
  const nav = navigator as Navigator & {
    connection?: { saveData?: boolean };
    deviceMemory?: number;
  };
  const saveData = !!nav.connection?.saveData;
  const lowMemory = typeof nav.deviceMemory === 'number' && nav.deviceMemory < 2;
  const small = typeof window !== 'undefined' && window.innerWidth < 768;
  return { webgl2, prefer3d: webgl2 && !saveData && !lowMemory && !small };
}
