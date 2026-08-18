export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export type HandShape = "open" | "fist" | "thumbUp" | "thumbDown" | "point";

export interface SkeletonPose {
  rightShoulder: Vec3;
  rightElbow: number;
  rightPalm: number;
  leftShoulder: Vec3;
  leftElbow: number;
  leftPalm: number;
  rightHand: HandShape;
  leftHand: HandShape;
  torsoLean: { x: number; z: number };
  rootOffset: Vec3;
}

export type EasingName = "linear" | "easeIn" | "easeOut" | "easeInOut";

export interface Keyframe {
  time: number;
  pose: SkeletonPose;
  easing?: EasingName;
}

export type MotionEffect =
  | {
      type: "trail";
      hand: "right" | "left";
      from: number;
      to: number;
      color?: string;
    }
  | {
      type: "flash";
      at: number;
      position: Vec3;
      color?: string;
    };

export interface MotionClip {
  code: string;
  duration: number;
  keyframes: Keyframe[];
  effects?: MotionEffect[];
  thumbTime?: number;
}

export const DEFAULT_POSE: SkeletonPose = {
  rightShoulder: { x: 0, y: 0, z: 0 },
  rightElbow: 0,
  rightPalm: 0,
  leftShoulder: { x: 0, y: 0, z: 0 },
  leftElbow: 0,
  leftPalm: 0,
  rightHand: "open",
  leftHand: "open",
  torsoLean: { x: 0, z: 0 },
  rootOffset: { x: 0, y: 0, z: 0 },
};

export function definePose(partial: Partial<SkeletonPose>): SkeletonPose {
  return {
    ...DEFAULT_POSE,
    ...partial,
    rightShoulder: { ...DEFAULT_POSE.rightShoulder, ...partial.rightShoulder },
    leftShoulder: { ...DEFAULT_POSE.leftShoulder, ...partial.leftShoulder },
    torsoLean: { ...DEFAULT_POSE.torsoLean, ...partial.torsoLean },
    rootOffset: { ...DEFAULT_POSE.rootOffset, ...partial.rootOffset },
  };
}
