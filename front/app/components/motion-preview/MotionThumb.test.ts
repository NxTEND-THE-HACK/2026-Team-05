import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToString } from "react-dom/server";
import { createElement } from "react";
import { MotionThumb } from "./MotionThumb";
import { MOTION_CLIPS } from "./motions";

test("MotionThumb renders an SVG skeleton for a known clip", () => {
  const html = renderToString(
    createElement(MotionThumb, { clip: MOTION_CLIPS["POSE_RIGHT_HAND_UP"] }),
  );
  assert.ok(html.includes("<svg"));
  assert.ok(html.includes("<circle"));
  assert.ok(html.includes("<polyline"));
});

test("MotionThumb renders a placeholder without a clip", () => {
  const html = renderToString(createElement(MotionThumb, {}));
  assert.ok(html.includes("No Preview"));
});
