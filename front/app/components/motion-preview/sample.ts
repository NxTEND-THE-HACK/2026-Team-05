import type { EasingName, MotionClip, SkeletonPose, Vec3 } from "./types";
import { lerpHandPose } from "./hand";

export const SKELETON = {
  shoulderWidth: 0.2,
  shoulderHeight: 0.55,
  neckHeight: 0.62,
  headRadius: 0.11,
  headGap: 0.05,
  upperArmLength: 0.28,
  forearmLength: 0.26,
  limbRadius: 0.045,
};

const DOWN: Vec3 = { x: 0, y: -1, z: 0 };

export function add(a: Vec3, b: Vec3): Vec3 {
  return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z };
}

export function scale(a: Vec3, s: number): Vec3 {
  return { x: a.x * s, y: a.y * s, z: a.z * s };
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function lerpVec3(a: Vec3, b: Vec3, t: number): Vec3 {
  return { x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t), z: lerp(a.z, b.z, t) };
}

export function rotateEuler(v: Vec3, e: Vec3): Vec3 {
  const c1 = Math.cos(e.x);
  const s1 = Math.sin(e.x);
  const c2 = Math.cos(e.y);
  const s2 = Math.sin(e.y);
  const c3 = Math.cos(e.z);
  const s3 = Math.sin(e.z);
  return {
    x: c2 * c3 * v.x - c2 * s3 * v.y + s2 * v.z,
    y:
      (c1 * s3 + c3 * s2 * s1) * v.x +
      (c1 * c3 - s1 * s2 * s3) * v.y -
      c2 * s1 * v.z,
    z:
      (s1 * s3 - c1 * c3 * s2) * v.x +
      (c3 * s1 + c1 * s2 * s3) * v.y +
      c1 * c2 * v.z,
  };
}

const EASINGS: Record<EasingName, (t: number) => number> = {
  linear: (t) => t,
  easeIn: (t) => t * t,
  easeOut: (t) => t * (2 - t),
  easeInOut: (t) => (t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t),
};

export function lerpPose(a: SkeletonPose, b: SkeletonPose, t: number): SkeletonPose {
  return {
    rightShoulder: lerpVec3(a.rightShoulder, b.rightShoulder, t),
    rightElbow: lerp(a.rightElbow, b.rightElbow, t),
    rightPalm: lerp(a.rightPalm, b.rightPalm, t),
    leftShoulder: lerpVec3(a.leftShoulder, b.leftShoulder, t),
    leftElbow: lerp(a.leftElbow, b.leftElbow, t),
    leftPalm: lerp(a.leftPalm, b.leftPalm, t),
    rightHand: lerpHandPose(a.rightHand, b.rightHand, t),
    leftHand: lerpHandPose(a.leftHand, b.leftHand, t),
    torsoLean: {
      x: lerp(a.torsoLean.x, b.torsoLean.x, t),
      z: lerp(a.torsoLean.z, b.torsoLean.z, t),
    },
    rootOffset: lerpVec3(a.rootOffset, b.rootOffset, t),
  };
}

export function sampleClip(clip: MotionClip, time: number): SkeletonPose {
  const kfs = clip.keyframes;
  if (kfs.length === 0) throw new Error(`clip ${clip.code} has no keyframes`);
  if (kfs.length === 1) return kfs[0].pose;

  const t = ((time % clip.duration) + clip.duration) % clip.duration;
  let i = 0;
  while (i < kfs.length - 1 && kfs[i + 1].time <= t) i++;
  const a = kfs[i];
  const b = kfs[i + 1] ?? a;
  if (b === a || b.time <= a.time) return a.pose;
  const raw = (t - a.time) / (b.time - a.time);
  return lerpPose(a.pose, b.pose, EASINGS[b.easing ?? "linear"](raw));
}

export interface SkeletonPoints {
  hips: Vec3;
  neck: Vec3;
  head: Vec3;
  rightShoulder: Vec3;
  rightElbow: Vec3;
  rightWrist: Vec3;
  leftShoulder: Vec3;
  leftElbow: Vec3;
  leftWrist: Vec3;
}

export function computeSkeletonPoints(pose: SkeletonPose): SkeletonPoints {
  const lean: Vec3 = { x: pose.torsoLean.x, y: 0, z: pose.torsoLean.z };
  const hips = pose.rootOffset;
  const neck = add(hips, rotateEuler({ x: 0, y: SKELETON.neckHeight, z: 0 }, lean));
  const head = add(neck, {
    x: 0,
    y: SKELETON.headGap + SKELETON.headRadius,
    z: 0,
  });

  const armPoints = (
    shoulderX: number,
    shoulderRot: Vec3,
    elbowFlex: number,
  ): { shoulder: Vec3; elbow: Vec3; wrist: Vec3 } => {
    const shoulder = add(
      hips,
      rotateEuler({ x: shoulderX, y: SKELETON.shoulderHeight, z: 0 }, lean),
    );
    const upperDir = rotateEuler(rotateEuler(DOWN, shoulderRot), lean);
    const elbow = add(shoulder, scale(upperDir, SKELETON.upperArmLength));
    const elbowRot: Vec3 = { x: -elbowFlex, y: 0, z: 0 };
    const foreDir = rotateEuler(
      rotateEuler(rotateEuler(DOWN, elbowRot), shoulderRot),
      lean,
    );
    const wrist = add(elbow, scale(foreDir, SKELETON.forearmLength));
    return { shoulder, elbow, wrist };
  };

  const right = armPoints(-SKELETON.shoulderWidth, pose.rightShoulder, pose.rightElbow);
  const left = armPoints(SKELETON.shoulderWidth, pose.leftShoulder, pose.leftElbow);

  return {
    hips,
    neck,
    head,
    rightShoulder: right.shoulder,
    rightElbow: right.elbow,
    rightWrist: right.wrist,
    leftShoulder: left.shoulder,
    leftElbow: left.elbow,
    leftWrist: left.wrist,
  };
}

export function sampleWristPositions(
  clip: MotionClip,
  hand: "right" | "left",
  from: number,
  to: number,
  samples = 24,
): Vec3[] {
  const points: Vec3[] = [];
  for (let i = 0; i <= samples; i++) {
    const t = from + ((to - from) * i) / samples;
    const pts = computeSkeletonPoints(sampleClip(clip, t));
    points.push(hand === "right" ? pts.rightWrist : pts.leftWrist);
  }
  return points;
}
