import assert from "node:assert/strict";
import { test } from "node:test";
import { MOTION_CLIPS } from "./motions";
import { computeSkeletonPoints, sampleClip } from "./sample";

const EXPECTED_CODES = [
  "POSE_RIGHT_HAND_UP",
  "POSE_LEFT_HAND_UP",
  "MOTION_SWIPE_RIGHT",
  "MOTION_SWIPE_LEFT",
  "MOTION_FINGER_SNAP",
  "MOTION_THUMBS_UP_MOVE_UP",
  "MOTION_THUMBS_DOWN_MOVE_DOWN",
  "MOTION_CLAP",
  "MOTION_OPEN_TO_FIST_DOWN",
  "MOTION_HAND_ROTATE_RIGHT",
  "MOTION_HAND_ROTATE_LEFT",
];

test("all 11 registered motions have a clip", () => {
  for (const code of EXPECTED_CODES) {
    assert.ok(MOTION_CLIPS[code], `missing clip for ${code}`);
  }
  assert.equal(Object.keys(MOTION_CLIPS).length, EXPECTED_CODES.length);
});

test("clips have well-formed keyframes and loop seamlessly", () => {
  for (const clip of Object.values(MOTION_CLIPS)) {
    assert.ok(clip.keyframes.length >= 2, `${clip.code}: needs >= 2 keyframes`);
    assert.ok(clip.keyframes[0].time === 0, `${clip.code}: first keyframe at t=0`);
    for (let i = 1; i < clip.keyframes.length; i++) {
      assert.ok(
        clip.keyframes[i].time > clip.keyframes[i - 1].time,
        `${clip.code}: keyframe times must increase`,
      );
    }
    assert.ok(
      clip.keyframes[clip.keyframes.length - 1].time <= clip.duration,
      `${clip.code}: last keyframe within duration`,
    );
    const first = clip.keyframes[0].pose;
    const last = clip.keyframes[clip.keyframes.length - 1].pose;
    assert.deepEqual(last, first, `${clip.code}: loop must be seamless`);
  }
});

test("sampling every clip over its duration yields finite skeleton points", () => {
  for (const clip of Object.values(MOTION_CLIPS)) {
    for (let i = 0; i <= 20; i++) {
      const t = (clip.duration * i) / 20;
      const pts = computeSkeletonPoints(sampleClip(clip, t));
      for (const p of Object.values(pts)) {
        assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y) && Number.isFinite(p.z));
      }
    }
  }
});
