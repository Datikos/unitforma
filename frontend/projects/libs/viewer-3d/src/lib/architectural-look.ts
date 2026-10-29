/**
 * The architectural look (ADR-0033): edges and ambient occlusion drawn by the viewer as
 * screen-space passes, so a 600k-triangle IFC model costs what a massing box costs. The scene is
 * drawn twice per frame: once flat-shaded into a normal + depth buffer, once for the colours;
 * GTAO and the edge pass read the first, the output pass writes sRGB to the canvas.
 */
import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { GTAOPass } from 'three/examples/jsm/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { Pass } from 'three/examples/jsm/postprocessing/Pass.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { ShaderPass } from 'three/examples/jsm/postprocessing/ShaderPass.js';

/** `full`: occlusion and edges; `edges`: edges only; `plain`: the renderer alone. */
export type RenderTier = 'full' | 'edges' | 'plain';

export interface DeviceFacts {
  webgl2: boolean;
  saveData: boolean;
  /** `navigator.deviceMemory` in GB; null when the browser does not say (Safari, Firefox). */
  deviceMemoryGb: number | null;
  viewportWidth: number;
}

/** Occlusion needs this much memory and a desktop-sized viewport (ADR-0033 Decision 4). */
export const FULL_TIER_MIN_MEMORY_GB = 4;
export const FULL_TIER_MIN_WIDTH_PX = 768;

/** A neighbouring pixel farther by this share of the depth is an edge. */
export const EDGE_DEPTH_RELATIVE = 0.02;
/** Normals apart by more than this many degrees are an edge (a crease). */
export const EDGE_NORMAL_DEGREES = 20;
export const EDGE_COLOUR = 0x334155;
export const EDGE_STRENGTH = 0.6;

/** GTAO in metres: the reach of the darkening under balconies and in recesses. */
export const AO_RADIUS_M = 2.0;
export const AO_SAMPLES = 16;
export const MSAA_SAMPLES = 4;

/** The tier a device gets, decided once per viewer (ADR-0033 Decision 4). */
export function renderTier(d: DeviceFacts): RenderTier {
  if (!d.webgl2) return 'plain';
  const memoryOk = d.deviceMemoryGb === null || d.deviceMemoryGb >= FULL_TIER_MIN_MEMORY_GB;
  if (!d.saveData && memoryOk && d.viewportWidth >= FULL_TIER_MIN_WIDTH_PX) return 'full';
  return 'edges';
}

/** What this browser says about itself; a canvas probe for WebGL2 like the portal's capabilities. */
export function deviceFacts(): DeviceFacts {
  let webgl2 = false;
  try {
    webgl2 = !!document.createElement('canvas').getContext('webgl2');
  } catch {
    webgl2 = false;
  }
  const nav = navigator as Navigator & {
    connection?: { saveData?: boolean };
    deviceMemory?: number;
  };
  return {
    webgl2,
    saveData: !!nav.connection?.saveData,
    deviceMemoryGb: typeof nav.deviceMemory === 'number' ? nav.deviceMemory : null,
    viewportWidth: typeof window !== 'undefined' ? window.innerWidth : 0,
  };
}

/**
 * Renders the scene flat-shaded into a normal + depth target. Meshes flagged `userData.ghost`
 * (units faded by the floor focus, drafts) and line objects are left out (ADR-0033 Decision 3).
 * Each mesh draws with a normal material of its own material's side: the massing and the plan
 * spaces are double-sided with walls wound inwards, and a front-sided override dropped them from
 * the buffer, so the edges of the units behind showed through the facade (2026-10-28, A-9/10).
 */
export class GBufferPass extends Pass {
  readonly target: THREE.WebGLRenderTarget;
  /** One normal material per `THREE.Side` (front, back, double). */
  private readonly materials = [THREE.FrontSide, THREE.BackSide, THREE.DoubleSide].map(
    (side) => new THREE.MeshNormalMaterial({ flatShading: true, blending: THREE.NoBlending, side }),
  );
  private readonly hidden: THREE.Object3D[] = [];
  private readonly swapped: [THREE.Mesh, THREE.Material | THREE.Material[]][] = [];

  constructor(
    private readonly scene: THREE.Scene,
    private readonly camera: THREE.Camera,
    width: number,
    height: number,
  ) {
    super();
    this.needsSwap = false;
    const depth = new THREE.DepthTexture(width, height);
    depth.format = THREE.DepthStencilFormat;
    depth.type = THREE.UnsignedInt248Type;
    this.target = new THREE.WebGLRenderTarget(width, height, {
      type: THREE.HalfFloatType,
      minFilter: THREE.NearestFilter,
      magFilter: THREE.NearestFilter,
      depthTexture: depth,
    });
  }

  get normalTexture(): THREE.Texture {
    return this.target.texture;
  }

  get depthTexture(): THREE.DepthTexture {
    return this.target.depthTexture as THREE.DepthTexture;
  }

  override render(renderer: THREE.WebGLRenderer): void {
    this.hidden.length = 0;
    this.swapped.length = 0;
    this.scene.traverse((o) => {
      if (!o.visible) return;
      if (o.userData['ghost'] || (o as THREE.Line).isLine) {
        o.visible = false;
        this.hidden.push(o);
        return;
      }
      const mesh = o as THREE.Mesh;
      if (!mesh.isMesh) return;
      this.swapped.push([mesh, mesh.material]);
      mesh.material = Array.isArray(mesh.material)
        ? mesh.material.map((m) => this.materials[m.side])
        : this.materials[mesh.material.side];
    });
    const background = this.scene.background;
    this.scene.background = null;
    renderer.setRenderTarget(this.target);
    renderer.setClearColor(0x7777ff, 1); // "straight at the camera", what GTAO expects of empty sky
    renderer.clear();
    renderer.render(this.scene, this.camera);
    renderer.setClearColor(0x000000, 0);
    this.scene.background = background;
    for (const [mesh, material] of this.swapped) mesh.material = material;
    for (const o of this.hidden) o.visible = true;
  }

  override setSize(width: number, height: number): void {
    this.target.setSize(width, height);
  }

  override dispose(): void {
    this.target.dispose();
    for (const m of this.materials) m.dispose();
  }
}

/** The edge shader: a depth or normal step between neighbouring pixels (ADR-0033 Decision 2). */
export const EDGE_SHADER = {
  uniforms: {
    tDiffuse: { value: null as THREE.Texture | null },
    tNormal: { value: null as THREE.Texture | null },
    tDepth: { value: null as THREE.Texture | null },
    resolution: { value: new THREE.Vector2(1, 1) },
    cameraNear: { value: 0.1 },
    cameraFar: { value: 1000 },
    edgeColor: { value: new THREE.Color(EDGE_COLOUR) },
    strength: { value: EDGE_STRENGTH },
    depthRelative: { value: EDGE_DEPTH_RELATIVE },
    normalCos: { value: Math.cos((EDGE_NORMAL_DEGREES * Math.PI) / 180) },
  },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: /* glsl */ `
    #include <packing>
    uniform sampler2D tDiffuse;
    uniform sampler2D tNormal;
    uniform sampler2D tDepth;
    uniform vec2 resolution;
    uniform float cameraNear;
    uniform float cameraFar;
    uniform vec3 edgeColor;
    uniform float strength;
    uniform float depthRelative;
    uniform float normalCos;
    varying vec2 vUv;

    float viewDepth(vec2 uv) {
      float d = texture2D(tDepth, uv).x;
      return -perspectiveDepthToViewZ(d, cameraNear, cameraFar);
    }
    vec3 viewNormal(vec2 uv) {
      return normalize(texture2D(tNormal, uv).xyz * 2.0 - 1.0);
    }

    void main() {
      vec4 colour = texture2D(tDiffuse, vUv);
      vec2 px = 1.0 / resolution;
      float z = viewDepth(vUv);
      vec3 n = viewNormal(vUv);
      vec2 offsets[4];
      offsets[0] = vec2(px.x, 0.0);
      offsets[1] = vec2(-px.x, 0.0);
      offsets[2] = vec2(0.0, px.y);
      offsets[3] = vec2(0.0, -px.y);
      float edge = 0.0;
      for (int i = 0; i < 4; i++) {
        vec2 uv = vUv + offsets[i];
        float zi = viewDepth(uv);
        // the nearer pixel owns the silhouette line, so it is one pixel wide
        if (zi - z > depthRelative * z) edge = 1.0;
        // a crease: both sides of it, where the depths agree
        else if (abs(zi - z) <= depthRelative * z && dot(n, viewNormal(uv)) < normalCos) edge = 1.0;
      }
      // the sky (depth 1) draws no line of its own
      if (texture2D(tDepth, vUv).x >= 1.0) edge = 0.0;
      gl_FragColor = vec4(mix(colour.rgb, edgeColor, edge * strength), colour.a);
    }
  `,
};

/** The edge pass keeps its resolution and the camera's near and far in step with the viewer. */
export class EdgePass extends ShaderPass {
  constructor(
    private readonly camera: THREE.PerspectiveCamera,
    gbuffer: GBufferPass,
  ) {
    super(
      new THREE.ShaderMaterial({
        uniforms: THREE.UniformsUtils.clone(EDGE_SHADER.uniforms),
        vertexShader: EDGE_SHADER.vertexShader,
        fragmentShader: EDGE_SHADER.fragmentShader,
      }),
    );
    this.uniforms['tNormal'].value = gbuffer.normalTexture;
    this.uniforms['tDepth'].value = gbuffer.depthTexture;
  }

  override setSize(width: number, height: number): void {
    (this.uniforms['resolution'].value as THREE.Vector2).set(width, height);
  }

  override render(
    renderer: THREE.WebGLRenderer,
    writeBuffer: THREE.WebGLRenderTarget,
    readBuffer: THREE.WebGLRenderTarget,
    deltaTime: number,
    maskActive: boolean,
  ): void {
    this.uniforms['cameraNear'].value = this.camera.near;
    this.uniforms['cameraFar'].value = this.camera.far;
    super.render(renderer, writeBuffer, readBuffer, deltaTime, maskActive);
  }
}

export interface LookChain {
  tier: Exclude<RenderTier, 'plain'>;
  composer: EffectComposer;
  /** CSS pixels; the composer multiplies by the renderer's pixel ratio. */
  setSize(width: number, height: number): void;
  /** The model's bounds, so occlusion samples stay inside it (GTAO `setSceneClipBox`). */
  setSceneBox(box: THREE.Box3 | null): void;
  dispose(): void;
}

/** Builds the pass chain for a tier; the scene is drawn twice per frame (G-buffer, colours). */
export function buildLookChain(
  renderer: THREE.WebGLRenderer,
  scene: THREE.Scene,
  camera: THREE.PerspectiveCamera,
  tier: Exclude<RenderTier, 'plain'>,
  width: number,
  height: number,
): LookChain {
  const ratio = renderer.getPixelRatio();
  const w = Math.max(1, Math.round(width * ratio));
  const h = Math.max(1, Math.round(height * ratio));
  const beauty = new THREE.WebGLRenderTarget(w, h, {
    type: THREE.HalfFloatType,
    samples: MSAA_SAMPLES,
  });
  const composer = new EffectComposer(renderer, beauty);
  composer.setPixelRatio(ratio);
  const gbuffer = new GBufferPass(scene, camera, w, h);
  composer.addPass(gbuffer);
  composer.addPass(new RenderPass(scene, camera));
  let gtao: GTAOPass | null = null;
  if (tier === 'full') {
    // r186's constructor crashes on an external G-buffer (`setGBuffer` reads its own target
    // for the debug output), so the pass builds its own first, then takes ours and drops its own
    gtao = new GTAOPass(scene, camera, w, h);
    gtao.setGBuffer(gbuffer.depthTexture, gbuffer.normalTexture);
    (
      gtao as unknown as { normalRenderTarget: THREE.WebGLRenderTarget }
    ).normalRenderTarget.dispose();
    gtao.output = GTAOPass.OUTPUT.Default;
    gtao.updateGtaoMaterial({ radius: AO_RADIUS_M, samples: AO_SAMPLES, screenSpaceRadius: false });
    composer.addPass(gtao);
  }
  composer.addPass(new EdgePass(camera, gbuffer));
  composer.addPass(new OutputPass());
  composer.setSize(width, height);
  return {
    tier,
    composer,
    setSize: (cw, ch) => composer.setSize(cw, ch),
    setSceneBox: (box) => {
      // the typed signature wants a box; the pass itself takes undefined to clear it
      (gtao as { setSceneClipBox(b: THREE.Box3 | undefined): void } | null)?.setSceneClipBox(
        box ?? undefined,
      );
    },
    dispose: () => {
      for (const p of composer.passes) p.dispose();
      composer.dispose();
    },
  };
}
