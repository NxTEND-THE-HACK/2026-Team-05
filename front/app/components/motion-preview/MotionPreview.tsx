import { lazy, Suspense, useEffect, useState } from "react";
import type { MotionClip } from "./types";

const MotionPlayer = lazy(() => import("./MotionPlayer"));

interface MotionPreviewProps {
  clip: MotionClip;
  height?: number | string;
  width?: number | string;
  interactive?: boolean;
}

export function MotionPreview({
  clip,
  height = 320,
  width = "100%",
  interactive = true,
}: MotionPreviewProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return <div style={{ width, height }} />;
  }

  return (
    <Suspense fallback={<div style={{ width, height }} />}>
      <MotionPlayer clip={clip} height={height} width={width} interactive={interactive} />
    </Suspense>
  );
}
