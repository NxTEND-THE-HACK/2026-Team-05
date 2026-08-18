import type { HandShape, SkeletonPose } from "./types";
import { SKELETON } from "./sample";

const BODY_COLOR = "#94a3b8";
const HEAD_COLOR = "#cbd5e1";
const RIGHT_HAND_COLOR = "#22d3ee";
const LEFT_HAND_COLOR = "#a78bfa";

const upperArmMiddle = SKELETON.upperArmLength - SKELETON.limbRadius * 2;
const forearmMiddle = SKELETON.forearmLength - SKELETON.limbRadius * 2;

function HandMesh({ shape, color }: { shape: HandShape; color: string }) {
  return (
    <group>
      {shape === "open" && (
        <mesh position={[0, -0.08, 0]}>
          <boxGeometry args={[0.13, 0.16, 0.025]} />
          <meshStandardMaterial color={color} />
        </mesh>
      )}
      {shape === "fist" && (
        <mesh position={[0, -0.05, 0]}>
          <sphereGeometry args={[0.065, 20, 20]} />
          <meshStandardMaterial color={color} />
        </mesh>
      )}
      {shape === "thumbUp" && (
        <group>
          <mesh position={[0, -0.05, 0]}>
            <sphereGeometry args={[0.065, 20, 20]} />
            <meshStandardMaterial color={color} />
          </mesh>
          <mesh position={[0, 0.03, 0]}>
            <capsuleGeometry args={[0.022, 0.07, 6, 12]} />
            <meshStandardMaterial color={color} />
          </mesh>
        </group>
      )}
      {shape === "thumbDown" && (
        <group>
          <mesh position={[0, -0.03, 0]}>
            <sphereGeometry args={[0.065, 20, 20]} />
            <meshStandardMaterial color={color} />
          </mesh>
          <mesh position={[0, -0.13, 0]}>
            <capsuleGeometry args={[0.022, 0.07, 6, 12]} />
            <meshStandardMaterial color={color} />
          </mesh>
        </group>
      )}
      {shape === "point" && (
        <group>
          <mesh position={[0, -0.05, 0]}>
            <sphereGeometry args={[0.065, 20, 20]} />
            <meshStandardMaterial color={color} />
          </mesh>
          <mesh position={[0, -0.13, 0]}>
            <capsuleGeometry args={[0.02, 0.08, 6, 12]} />
            <meshStandardMaterial color={color} />
          </mesh>
        </group>
      )}
    </group>
  );
}

interface ArmProps {
  shoulderX: number;
  shoulderRotation: [number, number, number];
  elbowFlex: number;
  palmRotation: number;
  hand: HandShape;
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
          <HandMesh shape={hand} color={handColor} />
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
