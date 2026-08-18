import assert from "node:assert/strict";
import { test } from "node:test";
import {
  computeSkeletonPoints,
  rotateEuler,
  sampleClip,
} from "./sample";
import { DEFAULT_POSE, definePose } from "./types";
import type { MotionClip } from "./types";

const clip: MotionClip = {
  code: "TEST",
  duration: 2,
  keyframes: [
    { time: 0, pose: DEFAULT_POSE },
    {
      time: 1,
      pose: definePose({ rightElbow: 1, rootOffset: { x: 0, y: 0.2, z: 0 } }),
    },
    { time: 2, pose: DEFAULT_POSE },
  ],
};

test("sampleClip returns exact keyframe poses at keyframe times", () => {
  assert.equal(sampleClip(clip, 0).rightElbow, 0);
  assert.equal(sampleClip(clip, 1).rightElbow, 1);
});

test("sampleClip interpolates between keyframes", () => {
  assert.ok(Math.abs(sampleClip(clip, 0.5).rightElbow - 0.5) < 1e-9);
});

test("sampleClip wraps time by duration", () => {
  assert.ok(Math.abs(sampleClip(clip, 2.5).rightElbow - 0.5) < 1e-9);
  assert.ok(Math.abs(sampleClip(clip, -0.5).rightElbow - 0.5) < 1e-9);
});

test("rotateEuler matches single-axis rotations", () => {
  const down = { x: 0, y: -1, z: 0 };
  const rz = rotateEuler(down, { x: 0, y: 0, z: Math.PI });
  assert.ok(Math.abs(rz.x) < 1e-9);
  assert.ok(Math.abs(rz.y - 1) < 1e-9);

  const rx = rotateEuler(down, { x: -Math.PI / 2, y: 0, z: 0 });
  assert.ok(Math.abs(rx.z - 1) < 1e-9);
});

test("default pose hangs arms straight down", () => {
  const pts = computeSkeletonPoints(DEFAULT_POSE);
  assert.ok(Math.abs(pts.rightWrist.x - pts.rightShoulder.x) < 1e-9);
  assert.ok(pts.rightWrist.y < pts.rightShoulder.y);
  assert.ok(Math.abs(pts.leftWrist.x - pts.leftShoulder.x) < 1e-9);
});

test("raising right shoulder z rotates the arm outward and up", () => {
  const raised = definePose({ rightShoulder: { x: 0, y: 0, z: -Math.PI } });
  const pts = computeSkeletonPoints(raised);
  assert.ok(pts.rightWrist.y > pts.rightShoulder.y);
});

test("positive elbow flexion moves the wrist forward", () => {
  const bent = definePose({ rightElbow: Math.PI / 2 });
  const pts = computeSkeletonPoints(bent);
  assert.ok(pts.rightWrist.z > 0.2);
});
