import { lazy, Suspense, useEffect, useState } from "react";
import type { MotionClip } from "./types";

const MotionPlayer = lazy(() => import("./MotionPlayer"));

interface MotionPreviewProps {
  clip: MotionClip;
  height?: number | string;
  interactive?: boolean;
}

export function MotionPreview({ clip, height = 320, interactive = true }: MotionPreviewProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return <div style={{ width: "100%", height }} />;
  }

  return (
    <Suspense fallback={<div style={{ width: "100%", height }} />}>
      <MotionPlayer clip={clip} height={height} interactive={interactive} />
    </Suspense>
  );
}
