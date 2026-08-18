import { computeSkeletonPoints, sampleClip, SKELETON } from "./sample";
import type { HandShape, MotionClip, Vec3 } from "./types";

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

function HandGlyph({
  shape,
  wrist,
  elbow,
  color,
  palm,
}: {
  shape: HandShape;
  wrist: Vec3;
  elbow: Vec3;
  color: string;
  palm: number;
}) {
  const [wx, wy] = px(wrist);
  const [ex, ey] = px(elbow);
  const dx = wx - ex;
  const dy = wy - ey;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;

  return (
    <g>
      {shape === "open" && (
        <ellipse
          cx={wx}
          cy={wy + 6}
          rx={Math.max(2, 7 * Math.abs(Math.cos(palm)))}
          ry={7}
          fill="none"
          stroke={color}
          strokeWidth={2.5}
        />
      )}
      {shape === "fist" && <circle cx={wx + ux * 5} cy={wy + uy * 5} r={5.5} fill={color} />}
      {shape === "thumbUp" && (
        <g>
          <circle cx={wx + ux * 5} cy={wy + uy * 5} r={5.5} fill={color} />
          <line x1={wx} y1={wy} x2={wx} y2={wy - 12} stroke={color} strokeWidth={3} strokeLinecap="round" />
        </g>
      )}
      {shape === "thumbDown" && (
        <g>
          <circle cx={wx + ux * 3} cy={wy + uy * 3} r={5.5} fill={color} />
          <line x1={wx} y1={wy + 4} x2={wx} y2={wy + 15} stroke={color} strokeWidth={3} strokeLinecap="round" />
        </g>
      )}
      {shape === "point" && (
        <g>
          <circle cx={wx + ux * 4} cy={wy + uy * 4} r={5.5} fill={color} />
          <line
            x1={wx + ux * 6}
            y1={wy + uy * 6}
            x2={wx + ux * 16}
            y2={wy + uy * 16}
            stroke={color}
            strokeWidth={3}
            strokeLinecap="round"
          />
        </g>
      )}
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
        shape={pose.rightHand}
        wrist={pts.rightWrist}
        elbow={pts.rightElbow}
        color={RIGHT_HAND_COLOR}
        palm={pose.rightPalm}
      />
      <HandGlyph
        shape={pose.leftHand}
        wrist={pts.leftWrist}
        elbow={pts.leftElbow}
        color={LEFT_HAND_COLOR}
        palm={pose.leftPalm}
      />
    </svg>
  );
}
