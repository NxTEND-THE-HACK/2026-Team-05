import { computeSkeletonPoints, sampleClip, SKELETON } from "./sample";
import type { MotionClip, Vec3 } from "./types";
import type { HandPose } from "./hand";

const W = 130;
const H = 150;
const SCALE = 80;
const BASE_Y = H - 22;

const BODY_COLOR = "#64748b";
const HEAD_COLOR = "#cbd5e1";
const RIGHT_HAND_COLOR = "#06b6d4";
const LEFT_HAND_COLOR = "#8b5cf6";

function px(p: Vec3): [number, number] {
  return [W / 2 + p.x * SCALE, BASE_Y - p.y * SCALE];
}

function rot2([x, y]: [number, number], ang: number): [number, number] {
  const c = Math.cos(ang);
  const s = Math.sin(ang);
  return [x * c - y * s, x * s + y * c];
}

function fingerPoints(
  wx: number,
  wy: number,
  dir: [number, number],
  curl: number,
  spread: number,
): string {
  const L = 5;
  const bend = curl * 1.2;
  let d = rot2(dir, spread);
  const pts: [number, number][] = [[wx, wy]];
  let px = wx;
  let py = wy;
  for (let i = 0; i < 3; i++) {
    if (i > 0) d = rot2(d, bend);
    px += d[0] * L;
    py += d[1] * L;
    pts.push([px, py]);
  }
  return pts.map(([x, y]) => `${x},${y}`).join(" ");
}

function HandGlyph({
  pose,
  wrist,
  elbow,
  color,
}: {
  pose: HandPose;
  wrist: Vec3;
  elbow: Vec3;
  color: string;
}) {
  const [wx, wy] = px(wrist);
  const [ex, ey] = px(elbow);
  const dx = wx - ex;
  const dy = wy - ey;
  const len = Math.hypot(dx, dy) || 1;
  const dir: [number, number] = [dx / len, dy / len];

  const thumbDir = rot2(dir, pose.thumbTilt + Math.PI / 2);
  const thumbX = wx + thumbDir[0] * 9;
  const thumbY = wy + thumbDir[1] * 9;

  return (
    <g>
      <polyline
        points={fingerPoints(wx, wy, dir, pose.index, -0.12)}
        fill="none"
        stroke={color}
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <polyline
        points={fingerPoints(wx, wy, dir, pose.middle, -0.04)}
        fill="none"
        stroke={color}
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <polyline
        points={fingerPoints(wx, wy, dir, pose.ring, 0.04)}
        fill="none"
        stroke={color}
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <polyline
        points={fingerPoints(wx, wy, dir, pose.pinky, 0.12)}
        fill="none"
        stroke={color}
        strokeWidth={2.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <line
        x1={wx}
        y1={wy}
        x2={thumbX}
        y2={thumbY}
        stroke={color}
        strokeWidth={2.4}
        strokeLinecap="round"
      />
    </g>
  );
}

interface MotionThumbProps {
  clip?: MotionClip;
  width?: number;
}

export function MotionThumb({ clip, width = 64 }: MotionThumbProps) {
  if (!clip) {
    return (
      <div
        style={{
          width,
          height: (width * H) / W,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#94a3b8",
          fontSize: 11,
          border: "1px dashed #cbd5e1",
          borderRadius: 6,
        }}
      >
        No Preview
      </div>
    );
  }

  const pose = sampleClip(clip, clip.thumbTime ?? clip.duration / 2);
  const pts = computeSkeletonPoints(pose);
  const [hipX, hipY] = px(pts.hips);
  const [neckX, neckY] = px(pts.neck);
  const [headX, headY] = px(pts.head);
  const [rsX, rsY] = px(pts.rightShoulder);
  const [reX, reY] = px(pts.rightElbow);
  const [rwX, rwY] = px(pts.rightWrist);
  const [lsX, lsY] = px(pts.leftShoulder);
  const [leX, leY] = px(pts.leftElbow);
  const [lwX, lwY] = px(pts.leftWrist);

  return (
    <svg
      width={width}
      height={(width * H) / W}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={clip.code}
    >
      <line x1={hipX} y1={hipY} x2={neckX} y2={neckY} stroke={BODY_COLOR} strokeWidth={11} strokeLinecap="round" />
      <circle cx={headX} cy={headY} r={SKELETON.headRadius * SCALE} fill={HEAD_COLOR} />
      <polyline
        points={`${rsX},${rsY} ${reX},${reY} ${rwX},${rwY}`}
        fill="none"
        stroke={BODY_COLOR}
        strokeWidth={7}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <polyline
        points={`${lsX},${lsY} ${leX},${leY} ${lwX},${lwY}`}
        fill="none"
        stroke={BODY_COLOR}
        strokeWidth={7}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <HandGlyph
        pose={pose.rightHand}
        wrist={pts.rightWrist}
        elbow={pts.rightElbow}
        color={RIGHT_HAND_COLOR}
      />
      <HandGlyph
        pose={pose.leftHand}
        wrist={pts.leftWrist}
        elbow={pts.leftElbow}
        color={LEFT_HAND_COLOR}
      />
    </svg>
  );
}
