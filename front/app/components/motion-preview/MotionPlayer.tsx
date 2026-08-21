import { useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Line, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import type { MotionClip, MotionEffect } from "./types";
import { sampleClip, sampleWristPositions } from "./sample";
import { Skeleton } from "./Skeleton";

function AnimatedSkeleton({ clip }: { clip: MotionClip }) {
  const [pose, setPose] = useState(() => sampleClip(clip, 0));
  useFrame(({ clock }) => {
    setPose(sampleClip(clip, clock.getElapsedTime()));
  });
  return <Skeleton pose={pose} />;
}

function Trail({
  clip,
  effect,
}: {
  clip: MotionClip;
  effect: Extract<MotionEffect, { type: "trail" }>;
}) {
  const points = useMemo(
    () =>
      sampleWristPositions(clip, effect.hand, effect.from, effect.to).map(
        (p) => [p.x, p.y, p.z] as [number, number, number],
      ),
    [clip, effect],
  );
  return (
    <Line
      points={points}
      color={effect.color ?? "#fbbf24"}
      lineWidth={3}
      transparent
      opacity={0.75}
    />
  );
}

const FLASH_DURATION = 0.35;

function Flash({
  clip,
  effect,
}: {
  clip: MotionClip;
  effect: Extract<MotionEffect, { type: "flash" }>;
}) {
  const mesh = useRef<THREE.Mesh>(null);
  const material = useRef<THREE.MeshBasicMaterial>(null);
  useFrame(({ clock }) => {
    if (!mesh.current || !material.current) return;
    const t = clock.getElapsedTime() % clip.duration;
    const age = t - effect.at;
    const active = age >= 0 && age < FLASH_DURATION;
    mesh.current.visible = active;
    if (active) {
      mesh.current.scale.setScalar(0.4 + (age / FLASH_DURATION) * 1.6);
      material.current.opacity = 1 - age / FLASH_DURATION;
    }
  });
  return (
    <mesh
      ref={mesh}
      position={[effect.position.x, effect.position.y, effect.position.z]}
      visible={false}
    >
      <sphereGeometry args={[0.12, 16, 16]} />
      <meshBasicMaterial
        ref={material}
        color={effect.color ?? "#fde047"}
        transparent
        opacity={0}
        depthWrite={false}
      />
    </mesh>
  );
}

interface MotionPlayerProps {
  clip: MotionClip;
  height?: number | string;
  width?: number | string;
  interactive?: boolean;
}

export default function MotionPlayer({
  clip,
  height = 320,
  width = "100%",
  interactive = true,
}: MotionPlayerProps) {
  return (
    <div style={{ width, height }}>
      <Canvas
        resize={{ offsetSize: true }}
        dpr={[1, 2]}
        camera={{ position: [0, 0.55, 2.6], fov: 35 }}
        gl={{ alpha: true, antialias: true }}
        onCreated={({ camera }) => camera.lookAt(0, 0.5, 0)}
      >
        <ambientLight intensity={0.8} />
        <directionalLight position={[2, 3, 4]} intensity={1.4} />
        <gridHelper args={[4, 16, "#334155", "#1e293b"]} position={[0, -0.02, 0]} />
        <AnimatedSkeleton clip={clip} />
        {clip.effects?.map((effect, i) =>
          effect.type === "trail" ? (
            <Trail key={i} clip={clip} effect={effect} />
          ) : (
            <Flash key={i} clip={clip} effect={effect} />
          ),
        )}
        {interactive && (
          <OrbitControls
            target={[0, 0.45, 0]}
            enablePan={false}
            minDistance={1.4}
            maxDistance={4.5}
          />
        )}
      </Canvas>
    </div>
  );
}
