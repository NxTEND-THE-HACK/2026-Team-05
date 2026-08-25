import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  reconcileOptimisticState,
  resolveDisplayStateValue,
} from "./displayState";

describe("resolveDisplayStateValue", () => {
  it("returns optimistic when defined", () => {
    assert.equal(
      resolveDisplayStateValue({ optimistic: true, rowState: undefined }),
      true,
    );
    assert.equal(
      resolveDisplayStateValue({ optimistic: false, rowState: undefined }),
      false,
    );
  });

  it("falls back to rowState.value when optimistic is undefined", () => {
    assert.equal(
      resolveDisplayStateValue({
        optimistic: undefined,
        rowState: { switchCode: "switch", online: true, value: true, source: "tuya" },
      }),
      true,
    );
    assert.equal(
      resolveDisplayStateValue({
        optimistic: undefined,
        rowState: { switchCode: "switch", online: true, value: false, source: "tuya" },
      }),
      false,
    );
  });

  it("returns 'unknown' when both are unavailable", () => {
    assert.equal(
      resolveDisplayStateValue({ optimistic: undefined, rowState: undefined }),
      "unknown",
    );
    assert.equal(
      resolveDisplayStateValue({
        optimistic: undefined,
        rowState: { switchCode: "switch", online: false, value: null, source: "tuya" },
      }),
      "unknown",
    );
  });

  it("prefers optimistic over actual state (race condition guard)", () => {
    // ユーザが ON を押したが invalidateQueries が古い false を返したケース
    // → optimistic を優先して ON のままにする
    assert.equal(
      resolveDisplayStateValue({
        optimistic: true,
        rowState: { switchCode: "switch", online: true, value: false, source: "tuya" },
      }),
      true,
    );
  });
});

describe("reconcileOptimisticState", () => {
  it("clears entries that match the actual value", () => {
    const prev = { "row-a": true, "row-b": false };
    const actual = { "row-a": true, "row-b": false };
    assert.deepEqual(reconcileOptimisticState(prev, actual), {});
  });

  it("keeps optimistic when actual value is still unavailable (undefined)", () => {
    const prev = { "row-a": true };
    // actual が undefined = まだ API から値が来ていない or null
    assert.deepEqual(reconcileOptimisticState(prev, { "row-a": undefined }), {
      "row-a": true,
    });
  });

  it("keeps optimistic when actual differs (stale Tuya value or physical change)", () => {
    // ユーザが ON を押した直後に invalidateQueries が古い false を返したケース。
    // この時 optimistic を残して UI の先祖返りを防ぐ。実機の反映は次の
    // ポーリングで true が届き、optimistic はその時点でクリアされる。
    const prev = { "row-a": true };
    const actual = { "row-a": false };
    assert.deepEqual(reconcileOptimisticState(prev, actual), { "row-a": true });
  });

  it("keeps optimistic for keys that are not in actual", () => {
    const prev = { "row-a": true, "row-b": false };
    const actual = { "row-a": true };
    assert.deepEqual(reconcileOptimisticState(prev, actual), { "row-b": false });
  });

  it("does not mutate the input", () => {
    const prev = { "row-a": true };
    const actual = { "row-a": false };
    const snapshot = { ...prev };
    reconcileOptimisticState(prev, actual);
    assert.deepEqual(prev, snapshot);
  });
});
