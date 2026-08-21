import type { MotionClip } from "./types";
import { definePose } from "./types";
import {
  HAND_FIST,
  HAND_OPEN,
  HAND_POINT,
  HAND_THUMB_DOWN,
  HAND_THUMB_UP,
  handPose,
} from "./hand";

const NEUTRAL = definePose({});

const RAISED_RIGHT = definePose({
  rightShoulder: { x: 0, y: 0, z: -2.75 },
  rightElbow: 0.25,
});

const poseRightHandUp: MotionClip = {
  code: "POSE_RIGHT_HAND_UP",
  duration: 2.8,
  thumbTime: 1.3,
  keyframes: [
    { time: 0, pose: NEUTRAL },
    { time: 0.7, pose: RAISED_RIGHT, easing: "easeOut" },
    { time: 1.9, pose: RAISED_RIGHT },
    { time: 2.6, pose: NEUTRAL, easing: "easeInOut" },
  ],
};

const RAISED_LEFT = definePose({
  leftShoulder: { x: 0, y: 0, z: 2.75 },
  leftElbow: 0.25,
});

const poseLeftHandUp: MotionClip = {
  code: "POSE_LEFT_HAND_UP",
  duration: 2.8,
  thumbTime: 1.3,
  keyframes: [
    { time: 0, pose: NEUTRAL },
    { time: 0.7, pose: RAISED_LEFT, easing: "easeOut" },
    { time: 1.9, pose: RAISED_LEFT },
    { time: 2.6, pose: NEUTRAL, easing: "easeInOut" },
  ],
};

const SWIPE_RIGHT_START = definePose({
  rightShoulder: { x: -0.9, y: 0, z: -0.3 },
  rightElbow: 1.4,
});

const SWIPE_RIGHT_END = definePose({
  rightShoulder: { x: -0.5, y: 0, z: -1.5 },
  rightElbow: 0.4,
});

const motionSwipeRight: MotionClip = {
  code: "MOTION_SWIPE_RIGHT",
  duration: 2.6,
  thumbTime: 1.1,
  keyframes: [
    { time: 0, pose: NEUTRAL },
    { time: 0.5, pose: SWIPE_RIGHT_START, easing: "easeOut" },
    { time: 1.1, pose: SWIPE_RIGHT_END, easing: "easeIn" },
    { time: 1.5, pose: SWIPE_RIGHT_END },
    { time: 2.3, pose: NEUTRAL, easing: "easeInOut" },
  ],
  effects: [{ type: "trail", hand: "right", from: 0.5, to: 1.1 }],
};

const SWIPE_LEFT_START = definePose({
  leftShoulder: { x: -0.9, y: 0, z: 0.3 },
  leftElbow: 1.4,
});

const SWIPE_LEFT_END = definePose({
  leftShoulder: { x: -0.5, y: 0, z: 1.5 },
  leftElbow: 0.4,
});

const motionSwipeLeft: MotionClip = {
  code: "MOTION_SWIPE_LEFT",
  duration: 2.6,
  thumbTime: 1.1,
  keyframes: [
    { time: 0, pose: NEUTRAL },
    { time: 0.5, pose: SWIPE_LEFT_START, easing: "easeOut" },
    { time: 1.1, pose: SWIPE_LEFT_END, easing: "easeIn" },
    { time: 1.5, pose: SWIPE_LEFT_END },
    { time: 2.3, pose: NEUTRAL, easing: "easeInOut" },
  ],
  effects: [{ type: "trail", hand: "left", from: 0.5, to: 1.1, color: "#34d399" }],
};

const SNAP_PREP = definePose({
  rightShoulder: { x: -1.6, y: 0, z: 0 },
  rightElbow: 1.9,
  rightHand: HAND_FIST,
});

const SNAP_PINCH = definePose({
  rightShoulder: { x: -1.6, y: 0, z: 0 },
  rightElbow: 1.9,
  rightHand: handPose({ thumb: 1, index: 0.3, middle: 0.95, ring: 1, pinky: 1 }),
});

const SNAP_FIRE = definePose({
  rightShoulder: { x: -1.6, y: 0, z: 0 },
  rightElbow: 1.9,
  rightHand: HAND_POINT,
});

const SNAP_RETRACT = definePose({
  rightShoulder: { x: -1.6, y: 0, z: 0 },
  rightElbow: 1.9,
  rightHand: HAND_FIST,
});

const motionFingerSnap: MotionClip = {
  code: "MOTION_FINGER_SNAP",
  duration: 2.6,
  thumbTime: 1.3,
  keyframes: [
    { time: 0, pose: NEUTRAL },
    { time: 0.6, pose: SNAP_PREP, easing: "easeOut" },
    { time: 1.05, pose: SNAP_PINCH },
    { time: 1.15, pose: SNAP_FIRE },
    { time: 1.6, pose: SNAP_FIRE },
    { time: 1.8, pose: SNAP_RETRACT },
    { time: 2.4, pose: NEUTRAL, easing: "easeInOut" },
  ],
  effects: [{ type: "flash", at: 1.15, position: { x: -0.2, y: 0.85, z: 0.2 } }],
};

const THUMB_UP_START = definePose({
  rightShoulder: { x: -1.5, y: 0, z: 0 },
  rightElbow: 0.9,
  rightHand: HAND_THUMB_UP,
});

const THUMB_UP_END = definePose({
  rightShoulder: { x: -2.6, y: 0, z: 0 },
  rightElbow: 0.5,
  rightHand: HAND_THUMB_UP,
});

const motionThumbsUpMoveUp: MotionClip = {
  code: "MOTION_THUMBS_UP_MOVE_UP",
  duration: 2.8,
  thumbTime: 1.7,
  keyframes: [
    { time: 0, pose: NEUTRAL },
    { time: 0.5, pose: THUMB_UP_START, easing: "easeOut" },
    { time: 0.9, pose: THUMB_UP_START },
    { time: 1.5, pose: THUMB_UP_END, easing: "easeOut" },
    { time: 2.0, pose: THUMB_UP_END },
    { time: 2.6, pose: NEUTRAL, easing: "easeInOut" },
  ],
  effects: [{ type: "trail", hand: "right", from: 0.9, to: 1.5 }],
};

const THUMB_DOWN_NEUTRAL = definePose({
  rightHand: HAND_THUMB_DOWN,
});

const THUMB_DOWN_START = definePose({
  rightShoulder: { x: -1.2, y: 0, z: 0 },
  rightElbow: 0.6,
  rightHand: HAND_THUMB_DOWN,
});

const THUMB_DOWN_END = definePose({
  rightShoulder: { x: -0.3, y: 0, z: -0.25 },
  rightElbow: 0.3,
  rightHand: HAND_THUMB_DOWN,
});

const motionThumbsDownMoveDown: MotionClip = {
  code: "MOTION_THUMBS_DOWN_MOVE_DOWN",
  duration: 2.8,
  thumbTime: 1.6,
  keyframes: [
    { time: 0, pose: THUMB_DOWN_NEUTRAL },
    { time: 0.5, pose: THUMB_DOWN_START, easing: "easeOut" },
    { time: 0.9, pose: THUMB_DOWN_START },
    { time: 1.5, pose: THUMB_DOWN_END, easing: "easeIn" },
    { time: 2.0, pose: THUMB_DOWN_END },
    { time: 2.6, pose: THUMB_DOWN_NEUTRAL, easing: "easeInOut" },
  ],
  effects: [{ type: "trail", hand: "right", from: 0.9, to: 1.5, color: "#f87171" }],
};

const CLAP_APART = definePose({
  rightShoulder: { x: -1.2, y: 0, z: -0.7 },
  rightElbow: 0.9,
  leftShoulder: { x: -1.2, y: 0, z: 0.7 },
  leftElbow: 0.9,
});

const CLAP_TOGETHER = definePose({
  rightShoulder: { x: -1.3, y: 0, z: 0.35 },
  rightElbow: 1.15,
  leftShoulder: { x: -1.3, y: 0, z: -0.35 },
  leftElbow: 1.15,
});

const motionClap: MotionClip = {
  code: "MOTION_CLAP",
  duration: 2.2,
  thumbTime: 0.8,
  keyframes: [
    { time: 0, pose: CLAP_APART },
    { time: 0.7, pose: CLAP_TOGETHER, easing: "easeOut" },
    { time: 1.0, pose: CLAP_TOGETHER },
    { time: 1.7, pose: CLAP_APART, easing: "easeInOut" },
  ],
  effects: [{ type: "flash", at: 0.72, position: { x: 0, y: 0.68, z: 0.42 } }],
};

const OPEN_FIST_TOP = definePose({
  rightShoulder: { x: -1.8, y: 0, z: 0 },
  rightElbow: 0.4,
  rightHand: HAND_OPEN,
});

const OPEN_FIST_MID = definePose({
  rightShoulder: { x: -1.2, y: 0, z: 0 },
  rightElbow: 0.55,
  rightHand: handPose({ thumb: 0.2, index: 0.1, middle: 0.4, ring: 0.6, pinky: 0.75 }),
});

const OPEN_FIST_BOTTOM = definePose({
  rightShoulder: { x: -0.6, y: 0, z: 0 },
  rightElbow: 0.7,
  rightHand: HAND_FIST,
});

const motionOpenToFistDown: MotionClip = {
  code: "MOTION_OPEN_TO_FIST_DOWN",
  duration: 2.8,
  thumbTime: 1.0,
  keyframes: [
    { time: 0, pose: NEUTRAL },
    { time: 0.5, pose: OPEN_FIST_TOP, easing: "easeOut" },
    { time: 0.9, pose: OPEN_FIST_TOP },
    { time: 1.2, pose: OPEN_FIST_MID },
    { time: 1.5, pose: OPEN_FIST_BOTTOM, easing: "easeIn" },
    { time: 1.9, pose: OPEN_FIST_BOTTOM },
    { time: 2.5, pose: NEUTRAL, easing: "easeInOut" },
  ],
  effects: [{ type: "trail", hand: "right", from: 0.9, to: 1.5, color: "#fb923c" }],
};

const ROTATE_RIGHT_ARM = definePose({
  rightShoulder: { x: -1.5, y: 0, z: 0 },
  rightElbow: 1.2,
  rightPalm: 0,
});

const ROTATE_RIGHT_TURNED = definePose({
  rightShoulder: { x: -1.5, y: 0, z: 0 },
  rightElbow: 1.2,
  rightPalm: -1.3,
});

const motionHandRotateRight: MotionClip = {
  code: "MOTION_HAND_ROTATE_RIGHT",
  duration: 3.6,
  thumbTime: 1.8,
  keyframes: [
    { time: 0, pose: NEUTRAL },
    { time: 0.6, pose: ROTATE_RIGHT_ARM, easing: "easeOut" },
    { time: 1.0, pose: ROTATE_RIGHT_ARM },
    { time: 1.6, pose: ROTATE_RIGHT_TURNED, easing: "easeInOut" },
    { time: 2.1, pose: ROTATE_RIGHT_TURNED },
    { time: 2.8, pose: ROTATE_RIGHT_ARM, easing: "easeInOut" },
    { time: 3.4, pose: NEUTRAL, easing: "easeInOut" },
  ],
};

const ROTATE_LEFT_ARM = definePose({
  leftShoulder: { x: -1.5, y: 0, z: 0 },
  leftElbow: 1.2,
  leftPalm: 0,
});

const ROTATE_LEFT_TURNED = definePose({
  leftShoulder: { x: -1.5, y: 0, z: 0 },
  leftElbow: 1.2,
  leftPalm: 1.3,
});

const motionHandRotateLeft: MotionClip = {
  code: "MOTION_HAND_ROTATE_LEFT",
  duration: 3.6,
  thumbTime: 1.8,
  keyframes: [
    { time: 0, pose: NEUTRAL },
    { time: 0.6, pose: ROTATE_LEFT_ARM, easing: "easeOut" },
    { time: 1.0, pose: ROTATE_LEFT_ARM },
    { time: 1.6, pose: ROTATE_LEFT_TURNED, easing: "easeInOut" },
    { time: 2.1, pose: ROTATE_LEFT_TURNED },
    { time: 2.8, pose: ROTATE_LEFT_ARM, easing: "easeInOut" },
    { time: 3.4, pose: NEUTRAL, easing: "easeInOut" },
  ],
};

export const MOTION_CLIPS: Record<string, MotionClip> = {
  [poseRightHandUp.code]: poseRightHandUp,
  [poseLeftHandUp.code]: poseLeftHandUp,
  [motionSwipeRight.code]: motionSwipeRight,
  [motionSwipeLeft.code]: motionSwipeLeft,
  [motionFingerSnap.code]: motionFingerSnap,
  [motionThumbsUpMoveUp.code]: motionThumbsUpMoveUp,
  [motionThumbsDownMoveDown.code]: motionThumbsDownMoveDown,
  [motionClap.code]: motionClap,
  [motionOpenToFistDown.code]: motionOpenToFistDown,
  [motionHandRotateRight.code]: motionHandRotateRight,
  [motionHandRotateLeft.code]: motionHandRotateLeft,
};

export function getMotionClip(code: string): MotionClip | undefined {
  return MOTION_CLIPS[code];
}
