import { describe, expect, it } from "vitest";

import {
  classifyFrame,
  createSignalState,
  DEFAULT_CONFIG,
  estimateYaw,
  estimatePitch,
  eyeAspectRatio,
  faceBox,
  laplacianVariance,
  mouthOpenness,
  type Landmark,
} from "./detector";

// --- synthetic landmarks ------------------------------------------------------
// Indices per MediaPipe face mesh: 1=nose, 33/133=left eye, 362/263=right eye,
// 159/145=left eyelid, 386/374=right eyelid, 61/291/13/14=mouth.
function makeFace(overrides?: Partial<Record<number, Partial<Landmark>>>): Landmark[] {
  const base: Landmark[] = Array.from({ length: 478 }, () => ({ x: 0.5, y: 0.5 }));
  base[1] = { x: 0.5, y: 0.58 }; // nose tip (centered between eyes)
  base[33] = { x: 0.32, y: 0.42 }; // left eye outer
  base[133] = { x: 0.42, y: 0.42 }; // left eye inner
  base[159] = { x: 0.37, y: 0.405 }; // left eye top
  base[145] = { x: 0.37, y: 0.435 }; // left eye bottom
  base[362] = { x: 0.68, y: 0.42 }; // right eye outer
  base[263] = { x: 0.58, y: 0.42 }; // right eye inner
  base[386] = { x: 0.63, y: 0.405 }; // right eye top
  base[374] = { x: 0.63, y: 0.435 }; // right eye bottom
  base[61] = { x: 0.36, y: 0.72 }; // mouth left
  base[291] = { x: 0.64, y: 0.72 }; // mouth right
  base[13] = { x: 0.5, y: 0.69 }; // mouth top
  base[14] = { x: 0.5, y: 0.75 }; // mouth bottom
  if (overrides) {
    for (const [index, patch] of Object.entries(overrides)) {
      const i = Number(index);
      base[i] = { ...base[i], ...patch };
    }
  }
  return base;
}

describe("faceBox", () => {
  it("computes a bounding box around landmarks", () => {
    const box = faceBox(makeFace());
    expect(box.width).toBeGreaterThan(0.2); // spans eyes ~0.32..0.58
    expect(box.minX).toBeLessThan(box.maxX);
  });
});

describe("estimateYaw", () => {
  it("is near zero for a frontal face", () => {
    expect(Math.abs(estimateYaw(makeFace()))).toBeLessThan(0.05);
  });

  it("is positive when the nose shifts toward one side", () => {
    const face = makeFace({ 1: { x: 0.58 } }); // nose toward right eye
    expect(estimateYaw(face)).toBeGreaterThan(0.1);
  });

  it("is negative when the nose shifts the other way", () => {
    const face = makeFace({ 1: { x: 0.42 } });
    expect(estimateYaw(face)).toBeLessThan(-0.1);
  });
});

describe("estimatePitch", () => {
  it("stays under the looking-down threshold for a forward-facing face", () => {
    expect(estimatePitch(makeFace())).toBeLessThan(0.75);
  });

  it("exceeds the looking-down threshold when the nose drops toward the chin", () => {
    const face = makeFace({ 1: { y: 0.72 } });
    expect(estimatePitch(face)).toBeGreaterThan(0.75);
  });
});

describe("eyeAspectRatio", () => {
  it("is ~0.25 for a normally-open eye", () => {
    const ear = eyeAspectRatio(makeFace());
    expect(ear).toBeGreaterThan(0.2);
    expect(ear).toBeLessThan(0.35);
  });

  it("drops under 0.19 for a closed eye", () => {
    const face = makeFace({
      159: { y: 0.42 }, 145: { y: 0.42 }, // left lid collapsed
      386: { y: 0.42 }, 374: { y: 0.42 }, // right lid collapsed
    });
    expect(eyeAspectRatio(face)).toBeLessThan(0.19);
  });
});

describe("mouthOpenness", () => {
  it("is low for a closed mouth", () => {
    expect(mouthOpenness(makeFace())).toBeLessThan(0.3);
  });

  it("exceeds 0.4 for an open mouth", () => {
    const face = makeFace({ 14: { y: 0.85 } }); // jaw dropped
    expect(mouthOpenness(face)).toBeGreaterThan(0.4);
  });
});

describe("laplacianVariance", () => {
  it("returns 0 for a flat (featureless) image", () => {
    const pixels = new Uint8ClampedArray(64 * 64).fill(128);
    expect(laplacianVariance(pixels, 64, 64)).toBe(0);
  });

  it("is high for a high-contrast (sharp) pattern", () => {
    const pixels = new Uint8ClampedArray(64 * 64);
    for (let i = 0; i < pixels.length; i++) {
      pixels[i] = ((Math.floor(i / 64) + Math.floor(i % 64)) % 2) * 255;
    }
    expect(laplacianVariance(pixels, 64, 64)).toBeGreaterThan(1000);
  });
});

describe("classifyFrame", () => {
  it("fires no_face after the condition holds long enough", () => {
    const state = createSignalState();
    const config = { ...DEFAULT_CONFIG, noFace: { minActiveMs: 1000, cooldownMs: 9999 } };
    // First frames: no fire yet.
    expect(classifyFrame(state, { timestampMs: 0, faces: [], config })).toHaveLength(0);
    expect(classifyFrame(state, { timestampMs: 500, faces: [], config })).toHaveLength(0);
    // At 1000 ms the condition has held long enough → fires once.
    const fired = classifyFrame(state, { timestampMs: 1000, faces: [], config });
    expect(fired).toHaveLength(1);
    expect(fired[0]?.signal).toBe("no_face");
    // Cooldown prevents immediate re-fire.
    expect(classifyFrame(state, { timestampMs: 1100, faces: [], config })).toHaveLength(0);
  });

  it("resets the episode when the condition clears before firing", () => {
    const state = createSignalState();
    const config = { ...DEFAULT_CONFIG, noFace: { minActiveMs: 1000, cooldownMs: 0 } };
    classifyFrame(state, { timestampMs: 0, faces: [], config });
    classifyFrame(state, { timestampMs: 500, faces: [makeFace()], config }); // cleared
    // A fresh episode starts from the next no-face frame.
    const fired = classifyFrame(state, { timestampMs: 1200, faces: [], config });
    expect(fired).toHaveLength(0); // only 200 ms into the new episode
  });

  it("fires multiple_faces with two faces", () => {
    const state = createSignalState();
    const config = { ...DEFAULT_CONFIG, multipleFaces: { minActiveMs: 0, cooldownMs: 0 } };
    const fired = classifyFrame(state, {
      timestampMs: 0,
      faces: [makeFace(), makeFace()],
      config,
    });
    expect(fired.map((o) => o.signal)).toContain("multiple_faces");
    expect(fired.find((o) => o.signal === "multiple_faces")?.detail?.faces).toBe(2);
  });

  it("fires looking_away when yaw exceeds the threshold", () => {
    const state = createSignalState();
    const config = { ...DEFAULT_CONFIG, lookingAway: { minActiveMs: 0, cooldownMs: 0, yawThreshold: 0.18 } };
    const turnedFace = makeFace({ 1: { x: 0.58 } }); // nose far from eye midpoint
    const fired = classifyFrame(state, { timestampMs: 0, faces: [turnedFace], config });
    expect(fired.map((o) => o.signal)).toContain("looking_away");
    expect(fired.find((o) => o.signal === "looking_away")?.detail?.direction).toBeTruthy();
  });

  it("fires eyes_closed when EAR is under the threshold", () => {
    const state = createSignalState();
    const config = { ...DEFAULT_CONFIG, eyesClosed: { minActiveMs: 0, cooldownMs: 0, earThreshold: 0.19 } };
    const closedFace = makeFace({
      159: { y: 0.42 }, 145: { y: 0.42 },
      386: { y: 0.42 }, 374: { y: 0.42 },
    });
    const fired = classifyFrame(state, { timestampMs: 0, faces: [closedFace], config });
    expect(fired.map((o) => o.signal)).toContain("eyes_closed");
  });

  it("fires speaking when the mouth is open past the threshold", () => {
    const state = createSignalState();
    const config = { ...DEFAULT_CONFIG, speaking: { minActiveMs: 0, cooldownMs: 0, opennessThreshold: 0.4 } };
    const openFace = makeFace({ 14: { y: 0.9 } });
    const fired = classifyFrame(state, { timestampMs: 0, faces: [openFace], config });
    expect(fired.map((o) => o.signal)).toContain("speaking");
  });

  it("fires video_blur when the Laplacian variance is below the threshold", () => {
    const state = createSignalState();
    const config = { ...DEFAULT_CONFIG, videoBlur: { minActiveMs: 0, cooldownMs: 0, varianceThreshold: 60 } };
    const fired = classifyFrame(state, {
      timestampMs: 0,
      faces: [makeFace()],
      blurVariance: 5,
      config,
    });
    expect(fired.map((o) => o.signal)).toContain("video_blur");
  });

  it("skips face-based signals when the face is too small", () => {
    const state = createSignalState();
    const config = {
      ...DEFAULT_CONFIG,
      minFaceWidth: 0.3,
      lookingAway: { minActiveMs: 0, cooldownMs: 0, yawThreshold: 0.18 },
    };
    const tinyFace = makeFace({ 33: { x: 0.48 }, 362: { x: 0.52 } }); // very narrow face
    const fired = classifyFrame(state, { timestampMs: 0, faces: [tinyFace], config });
    expect(fired.map((o) => o.signal)).not.toContain("looking_away");
  });

  it("respects the cooldown across separate episodes", () => {
    const state = createSignalState();
    const config = { ...DEFAULT_CONFIG, noFace: { minActiveMs: 0, cooldownMs: 5000 } };
    classifyFrame(state, { timestampMs: 0, faces: [], config }); // fires
    classifyFrame(state, { timestampMs: 100, faces: [makeFace()], config }); // clears
    const second = classifyFrame(state, { timestampMs: 2000, faces: [], config });
    expect(second).toHaveLength(0); // within cooldown window
  });
});
