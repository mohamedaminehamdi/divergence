"use client";

import { useEffect, useRef } from "react";

/* A WebGL particle sphere fixed behind the landing page.

   Three populations, all moved on the GPU from time alone, so the CPU only sets
   a handful of uniforms per frame:
     shell     the sphere's skin: evenly spread dots that breathe and turn
     outbound  dots that peel off the surface and spiral outward, fading
     inbound   dots that stream in from beyond the screen and are absorbed

   Blending is additive, so where the streams cross the surface they flare. The
   sphere sits right of the headline in the hero and drifts to centre and dims as
   the page scrolls, so every section sits on the same object. Colours are read
   from the theme's --color-orb-* tokens, so a palette change reaches it too. */

const SHELL = 6000;
const OUTBOUND = 3500;
const INBOUND = 3500;
const STRIDE = 8; // dir.xyz, seed, kind, speed, hue, tail
const TRAIL = 0.02; // how far behind the head a trail's tail sits, in life fraction

const VERT = `
attribute vec3 a_dir;
attribute float a_seed;
attribute float a_kind;
attribute float a_speed;
attribute float a_hue;
attribute float a_tail;

uniform float u_time;
uniform vec2 u_res;
uniform vec2 u_center;
uniform float u_radius;
uniform vec2 u_tilt;
uniform float u_dpr;
uniform float u_trail;

varying float v_alpha;
varying float v_hue;

mat3 rotY(float a) { float c = cos(a); float s = sin(a); return mat3(c, 0.0, -s, 0.0, 1.0, 0.0, s, 0.0, c); }
mat3 rotX(float a) { float c = cos(a); float s = sin(a); return mat3(1.0, 0.0, 0.0, 0.0, c, s, 0.0, -s, c); }

void main() {
  float t = fract(u_time * a_speed + a_seed);
  t = max(t - a_tail * u_trail, 0.0);
  vec3 d = a_dir;
  float r;
  float a;
  float size;

  if (a_kind < 0.5) {
    r = 1.0 + 0.045 * sin(u_time * 1.7 + a_seed * 31.0);
    a = 0.85;
    size = 3.0;
  } else if (a_kind < 1.5) {
    float e = t * t;
    r = 1.0 + e * 1.55;
    d = rotY(t * 1.8) * d;
    a = (1.0 - t) * smoothstep(0.0, 0.06, t);
    size = 4.2;
  } else {
    float e = 1.0 - (1.0 - t) * (1.0 - t);
    r = 2.6 - e * 1.6;
    d = rotY(-(1.0 - t) * 2.0) * d;
    a = smoothstep(0.0, 0.25, t) * (1.0 - smoothstep(0.9, 1.0, t)) * 0.9;
    size = 3.8;
  }

  vec3 p = rotX(0.4 + u_tilt.y) * rotY(u_time * 0.24 + u_tilt.x) * (d * r);
  float persp = 5.0 / (5.0 - p.z);
  vec2 screen = u_center + vec2(p.x, -p.y) * u_radius * persp;
  vec2 clip = screen / u_res * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);

  float facing = clamp(p.z / max(r, 0.001) * 0.5 + 0.5, 0.0, 1.0);
  v_alpha = a * (0.2 + 0.8 * facing) * (1.0 - a_tail);
  v_hue = a_hue;
  gl_PointSize = size * persp * u_dpr * (0.65 + 0.7 * facing);
}
`;

const FRAG = `
precision mediump float;
uniform vec3 u_c1;
uniform vec3 u_c2;
uniform vec3 u_c3;
uniform float u_gain;
uniform float u_lines;
varying float v_alpha;
varying float v_hue;

void main() {
  vec3 col = v_hue < 0.55 ? u_c1 : (v_hue < 0.85 ? u_c2 : u_c3);
  if (u_lines > 0.5) {
    gl_FragColor = vec4(col * v_alpha * u_gain * 0.5, 1.0);
    return;
  }
  float d = length(gl_PointCoord - 0.5);
  if (d > 0.5) discard;
  float halo = smoothstep(0.5, 0.0, d);
  float glow = halo * halo * 0.55 + smoothstep(0.2, 0.0, d) * 0.9;
  gl_FragColor = vec4(col * glow * v_alpha * u_gain, 1.0);
}
`;

/* Deterministic, so the sphere is the same on every load. */
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function buildParticles(): Float32Array {
  const rand = mulberry32(7);
  const total = SHELL + OUTBOUND + INBOUND;
  const data = new Float32Array(total * STRIDE);
  const golden = Math.PI * (3 - Math.sqrt(5));
  const randomDir = (): [number, number, number] => {
    const z = rand() * 2 - 1;
    const a = rand() * Math.PI * 2;
    const s = Math.sqrt(1 - z * z);
    return [Math.cos(a) * s, Math.sin(a) * s, z];
  };

  let o = 0;
  const push = (dir: [number, number, number], kind: number, speed: number, hue: number) => {
    data[o++] = dir[0];
    data[o++] = dir[1];
    data[o++] = dir[2];
    data[o++] = rand();
    data[o++] = kind;
    data[o++] = speed;
    data[o++] = hue;
    data[o++] = 0;
  };

  // Shell on a Fibonacci lattice, so the skin is even rather than clumped.
  for (let i = 0; i < SHELL; i++) {
    const y = 1 - (i / (SHELL - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    push([Math.cos(golden * i) * r, y, Math.sin(golden * i) * r], 0, 0.05, rand());
  }
  // Outbound sparks are cyan and white; inbound streams are mostly blue.
  for (let i = 0; i < OUTBOUND; i++) {
    const hue = rand() < 0.75 ? rand() * 0.55 : 0.85 + rand() * 0.15;
    push(randomDir(), 1, 0.11 + rand() * 0.22, hue);
  }
  for (let i = 0; i < INBOUND; i++) {
    const hue = rand() < 0.8 ? 0.55 + rand() * 0.3 : rand() * 0.55;
    push(randomDir(), 2, 0.09 + rand() * 0.2, hue);
  }
  return data;
}

/* Head and tail vertices for every travelling particle, drawn as lines so the
   streams read as movement even in a still frame. */
function buildTrails(points: Float32Array): Float32Array {
  const moving = OUTBOUND + INBOUND;
  const out = new Float32Array(moving * 2 * STRIDE);
  let o = 0;
  for (let i = SHELL; i < SHELL + moving; i++) {
    for (const tail of [0, 1]) {
      for (let k = 0; k < STRIDE - 1; k++) out[o++] = points[i * STRIDE + k];
      out[o++] = tail;
    }
  }
  return out;
}

function readColor(name: string, fallback: string): [number, number, number] {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  const hex = raw.startsWith("#") ? raw.slice(1) : fallback.slice(1);
  const n = parseInt(hex.length === 3 ? hex.replace(/./g, "$&$&") : hex, 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

function compile(gl: WebGLRenderingContext, type: number, src: string) {
  const s = gl.createShader(type)!;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(s) || "shader compile failed");
  }
  return s;
}

export default function ParticleSphere() {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { alpha: false, antialias: false });
    // No WebGL: the page still works on its plain ground.
    if (!gl) return;

    let program: WebGLProgram;
    try {
      program = gl.createProgram()!;
      gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERT));
      gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAG));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return;
    } catch {
      return;
    }
    gl.useProgram(program);

    const data = buildParticles();
    const count = data.length / STRIDE;
    const trails = buildTrails(data);
    const trailCount = trails.length / STRIDE;
    const pointBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, pointBuf);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    const trailBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, trailBuf);
    gl.bufferData(gl.ARRAY_BUFFER, trails, gl.STATIC_DRAW);

    const bytes = STRIDE * 4;
    const layout: [string, number, number][] = [
      ["a_dir", 3, 0], ["a_seed", 1, 3], ["a_kind", 1, 4],
      ["a_speed", 1, 5], ["a_hue", 1, 6], ["a_tail", 1, 7],
    ];
    const locs = layout.map(([name]) => gl.getAttribLocation(program, name));
    locs.forEach((loc) => gl.enableVertexAttribArray(loc));
    // Both buffers share one layout, so switching is a rebind plus pointers.
    const bind = (buf: WebGLBuffer | null) => {
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      layout.forEach(([, size, offset], i) =>
        gl.vertexAttribPointer(locs[i], size, gl.FLOAT, false, bytes, offset * 4),
      );
    };

    const u = (name: string) => gl.getUniformLocation(program, name);
    const uTime = u("u_time");
    const uRes = u("u_res");
    const uCenter = u("u_center");
    const uRadius = u("u_radius");
    const uTilt = u("u_tilt");
    const uDpr = u("u_dpr");
    const uGain = u("u_gain");
    const uLines = u("u_lines");
    gl.uniform1f(u("u_trail"), TRAIL);

    gl.uniform3fv(u("u_c1"), readColor("--color-orb-1", "#a58cff"));
    gl.uniform3fv(u("u_c2"), readColor("--color-orb-2", "#5b7cff"));
    gl.uniform3fv(u("u_c3"), readColor("--color-orb-3", "#eaf2f8"));
    const ground = readColor("--color-ground", "#05070b");

    gl.disable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let dpr = 1;
    let raf = 0;
    const tilt = { x: 0, y: 0, tx: 0, ty: 0 };
    const start = performance.now();

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(window.innerWidth * dpr);
      canvas.height = Math.round(window.innerHeight * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
    };

    const frame = (seconds: number) => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      const wide = w >= 1024;
      // 0 in the hero, 1 once a screen has scrolled past.
      const past = Math.min(1, window.scrollY / (h * 0.9));
      const ease = past * past * (3 - 2 * past);
      const heroX = wide ? w * 0.7 : w * 0.5;
      const cx = heroX + (w * 0.5 - heroX) * ease;
      // On phones the words stack over the sphere, so it sits low, behind the buttons.
      const cy = h * (wide ? 0.52 : 0.8);
      const radius = wide ? Math.min(w * 0.2, h * 0.32) : Math.min(w * 0.36, h * 0.22);

      tilt.x += (tilt.tx - tilt.x) * 0.05;
      tilt.y += (tilt.ty - tilt.y) * 0.05;

      gl.clearColor(ground[0], ground[1], ground[2], 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform1f(uTime, seconds);
      gl.uniform2f(uRes, w, h);
      gl.uniform2f(uCenter, cx, cy);
      gl.uniform1f(uRadius, radius);
      gl.uniform2f(uTilt, tilt.x, tilt.y);
      gl.uniform1f(uDpr, dpr);
      gl.uniform1f(uGain, 1 - 0.62 * ease);

      bind(trailBuf);
      gl.uniform1f(uLines, 1);
      gl.drawArrays(gl.LINES, 0, trailCount);

      bind(pointBuf);
      gl.uniform1f(uLines, 0);
      gl.drawArrays(gl.POINTS, 0, count);
    };

    const loop = (now: number) => {
      frame((now - start) / 1000);
      raf = requestAnimationFrame(loop);
    };

    // The sphere leans gently toward the pointer.
    const onPointer = (e: PointerEvent) => {
      tilt.tx = (e.clientX / window.innerWidth - 0.5) * 0.7;
      tilt.ty = (e.clientY / window.innerHeight - 0.5) * 0.4;
    };

    resize();
    if (reduced) {
      // One still frame. Scroll and resize only re-place it.
      frame(14);
    } else {
      raf = requestAnimationFrame(loop);
      window.addEventListener("pointermove", onPointer, { passive: true });
    }

    const onResize = () => {
      resize();
      if (reduced) frame(14);
    };
    const onScroll = () => {
      if (reduced) frame(14);
    };
    window.addEventListener("resize", onResize);
    window.addEventListener("scroll", onScroll, { passive: true });

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

  return (
    <canvas
      ref={ref}
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10 h-full w-full"
    />
  );
}
