import type { SkeletonPose } from "./types";
import type { HandPose } from "./hand";
import { SKELETON } from "./sample";

const BODY_COLOR = "#94a3b8";
const HEAD_COLOR = "#cbd5e1";
const RIGHT_HAND_COLOR = "#22d3ee";
const LEFT_HAND_COLOR = "#a78bfa";

const upperArmMiddle = SKELETON.upperArmLength - SKELETON.limbRadius * 2;
const forearmMiddle = SKELETON.forearmLength - SKELETON.limbRadius * 2;

const FINGER_RADIUS = 0.014;
const FINGER_SEGMENT = 0.055;
const FINGER_BEND = Math.PI / 2.4;
const THUMB_BEND = Math.PI / 2.8;

function Segment({ length, radius, color }: { length: number; radius: number; color: string }) {
  return (
    <mesh position={[0, -length / 2, 0]}>
      <capsuleGeometry args={[radius, length - radius * 2, 4, 8]} />
      <meshStandardMaterial color={color} />
    </mesh>
  );
}

function Finger({ curl, spread, color }: { curl: number; spread: number; color: string }) {
  const bend = curl * FINGER_BEND;
  return (
    <group rotation={[0, 0, spread]}>
      <Segment length={FINGER_SEGMENT} radius={FINGER_RADIUS} color={color} />
      <group position={[0, -FINGER_SEGMENT, 0]} rotation={[bend, 0, 0]}>
        <Segment length={FINGER_SEGMENT} radius={FINGER_RADIUS} color={color} />
        <group position={[0, -FINGER_SEGMENT, 0]} rotation={[bend, 0, 0]}>
          <Segment length={FINGER_SEGMENT} radius={FINGER_RADIUS} color={color} />
        </group>
      </group>
    </group>
  );
}

function Thumb({ pose, color }: { pose: HandPose; color: string }) {
  const bend = pose.thumb * THUMB_BEND;
  return (
    <group position={[0.055, 0.015, 0]} rotation={[0, 0, Math.PI / 2 + pose.thumbTilt]}>
      <Segment length={FINGER_SEGMENT} radius={FINGER_RADIUS} color={color} />
      <group position={[0, -FINGER_SEGMENT, 0]} rotation={[bend, 0, 0]}>
        <Segment length={FINGER_SEGMENT} radius={FINGER_RADIUS} color={color} />
      </group>
    </group>
  );
}

function Hand({ pose, color }: { pose: HandPose; color: string }) {
  return (
    <group>
      <mesh position={[0, -0.035, 0]}>
        <boxGeometry args={[0.1, 0.075, 0.04]} />
        <meshStandardMaterial color={color} />
      </mesh>
      <group position={[-0.04, -0.055, 0]}>
        <Finger curl={pose.index} spread={-0.1} color={color} />
      </group>
      <group position={[-0.013, -0.055, 0]}>
        <Finger curl={pose.middle} spread={0} color={color} />
      </group>
      <group position={[0.013, -0.055, 0]}>
        <Finger curl={pose.ring} spread={0} color={color} />
      </group>
      <group position={[0.04, -0.055, 0]}>
        <Finger curl={pose.pinky} spread={0.1} color={color} />
      </group>
      <Thumb pose={pose} color={color} />
    </group>
  );
}

interface ArmProps {
  shoulderX: number;
  shoulderRotation: [number, number, number];
  elbowFlex: number;
  palmRotation: number;
  hand: HandPose;
  handColor: string;
}

function Arm({
  shoulderX,
  shoulderRotation,
  elbowFlex,
  palmRotation,
  hand,
  handColor,
}: ArmProps) {
  return (
    <group
      position={[shoulderX, SKELETON.shoulderHeight, 0]}
      rotation={shoulderRotation}
    >
      <mesh position={[0, -SKELETON.upperArmLength / 2, 0]}>
        <capsuleGeometry args={[SKELETON.limbRadius, upperArmMiddle, 6, 12]} />
        <meshStandardMaterial color={BODY_COLOR} />
      </mesh>
      <group position={[0, -SKELETON.upperArmLength, 0]} rotation={[-elbowFlex, 0, 0]}>
        <mesh position={[0, -SKELETON.forearmLength / 2, 0]}>
          <capsuleGeometry args={[SKELETON.limbRadius, forearmMiddle, 6, 12]} />
          <meshStandardMaterial color={BODY_COLOR} />
        </mesh>
        <group position={[0, -SKELETON.forearmLength, 0]} rotation={[0, palmRotation, 0]}>
          <Hand pose={hand} color={handColor} />
        </group>
      </group>
    </group>
  );
}

export function Skeleton({ pose }: { pose: SkeletonPose }) {
  return (
    <group position={[pose.rootOffset.x, pose.rootOffset.y, pose.rootOffset.z]}>
      <group rotation={[pose.torsoLean.x, 0, pose.torsoLean.z]}>
        <mesh position={[0, SKELETON.neckHeight / 2, 0]}>
          <capsuleGeometry args={[0.09, SKELETON.neckHeight - 0.18, 6, 16]} />
          <meshStandardMaterial color={BODY_COLOR} />
        </mesh>
        <mesh position={[0, SKELETON.neckHeight + SKELETON.headGap + SKELETON.headRadius, 0]}>
          <sphereGeometry args={[SKELETON.headRadius, 24, 24]} />
          <meshStandardMaterial color={HEAD_COLOR} />
        </mesh>
        <Arm
          shoulderX={-SKELETON.shoulderWidth}
          shoulderRotation={[pose.rightShoulder.x, pose.rightShoulder.y, pose.rightShoulder.z]}
          elbowFlex={pose.rightElbow}
          palmRotation={pose.rightPalm}
          hand={pose.rightHand}
          handColor={RIGHT_HAND_COLOR}
        />
        <Arm
          shoulderX={SKELETON.shoulderWidth}
          shoulderRotation={[pose.leftShoulder.x, pose.leftShoulder.y, pose.leftShoulder.z]}
          elbowFlex={pose.leftElbow}
          palmRotation={pose.leftPalm}
          hand={pose.leftHand}
          handColor={LEFT_HAND_COLOR}
        />
      </group>
    </group>
  );
}
