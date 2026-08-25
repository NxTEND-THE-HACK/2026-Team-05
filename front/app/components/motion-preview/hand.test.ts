import assert from "node:assert/strict";
import { test } from "node:test";
import {
  HAND_FIST,
  HAND_OPEN,
  HAND_POINT,
  HAND_THUMB_DOWN,
  HAND_THUMB_UP,
  lerpHandPose,
} from "./hand";
import { MOTION_CLIPS } from "./motions";
import { sampleClip } from "./sample";

const CURL_KEYS = ["thumb", "index", "middle", "ring", "pinky"] as const;

test("lerpHandPose interpolates halfway between presets", () => {
  const mid = lerpHandPose(HAND_OPEN, HAND_FIST, 0.5);
  assert.ok(Math.abs(mid.index - 0.5) < 1e-9);
  assert.ok(Math.abs(mid.pinky - 0.5) < 1e-9);
});

test("hand presets are well-formed", () => {
  assert.equal(HAND_OPEN.index, 0);
  assert.equal(HAND_FIST.index, 1);
  assert.equal(HAND_POINT.index, 0);
  assert.equal(HAND_POINT.middle, 1);
  assert.ok(HAND_THUMB_UP.thumbTilt < 0, "thumbs-up points distal (up when arm raised)");
  assert.ok(HAND_THUMB_DOWN.thumbTilt < 0, "thumbs-down points distal (down when arm lowered)");
});

test("sampling every clip keeps hand values finite and curls in range", () => {
  for (const clip of Object.values(MOTION_CLIPS)) {
    for (let i = 0; i <= 20; i++) {
      const t = (clip.duration * i) / 20;
      const pose = sampleClip(clip, t);
      for (const hand of [pose.rightHand, pose.leftHand]) {
        for (const key of CURL_KEYS) {
          assert.ok(Number.isFinite(hand[key]), `${clip.code}: ${key} finite`);
          assert.ok(
            hand[key] >= -1e-6 && hand[key] <= 1 + 1e-6,
            `${clip.code}: ${key} in [0,1]`,
          );
        }
        assert.ok(Number.isFinite(hand.thumbTilt), `${clip.code}: thumbTilt finite`);
      }
    }
  }
});
