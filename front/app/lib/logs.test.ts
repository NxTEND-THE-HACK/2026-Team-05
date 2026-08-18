import { describe, it } from "node:test";
import assert from "node:assert/strict";
import type { ActionLog } from "~/types/backendApi";
import { mergeLogList } from "./logs";

const createLog = (id: string): ActionLog => ({
  id,
  eventId: id,
  cameraId: "demo-camera-1",
  motionCode: "POSE_RIGHT_HAND_UP",
  status: "SUCCESS",
  detectedAt: "2026-08-18T00:00:00Z",
});

describe("mergeLogList", () => {
  it("keeps an SSE log when applied to a stale HTTP response", () => {
    const existing = createLog("existing");
    const latest = createLog("latest");

    assert.deepEqual(mergeLogList([existing], latest, 100), [latest, existing]);
  });

  it("deduplicates an SSE log and respects the limit", () => {
    const existing = createLog("existing");
    const latest = createLog("latest");

    assert.deepEqual(mergeLogList([latest, existing], latest, 1), [latest]);
  });
});
