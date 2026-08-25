import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  groupActionsIntoRows,
  isRowToggleable,
} from "./controlRows";
import type { TuyaAction } from "~/types/backendApi";

function makeAction(
  id: string,
  applianceId: string,
  value: boolean | undefined,
  switchCode: string = "switch",
  name?: string,
): TuyaAction {
  return {
    id,
    applianceId,
    name: name ?? `${applianceId}-${id}`,
    providerType: "TUYA",
    params: { value, switchCode },
  };
}

describe("groupActionsIntoRows", () => {
  it("returns empty array when given no actions", () => {
    assert.deepEqual(groupActionsIntoRows([]), []);
  });

  it("groups on/off pair for the same (applianceId, switchCode)", () => {
    const rows = groupActionsIntoRows([
      makeAction("on", "plug-a", true),
      makeAction("off", "plug-a", false),
    ]);
    assert.equal(rows.length, 1);
    assert.equal(rows[0].onAction?.id, "on");
    assert.equal(rows[0].offAction?.id, "off");
    assert.equal(isRowToggleable(rows[0]), true);
  });

  it("separates rows by switchCode to avoid clobbering", () => {
    const rows = groupActionsIntoRows([
      makeAction("on1", "plug-a", true, "switch_1"),
      makeAction("on2", "plug-a", true, "switch_2"),
      makeAction("off1", "plug-a", false, "switch_1"),
    ]);
    assert.equal(rows.length, 2);
    const codes = rows.map((r) => r.onAction?.params.switchCode).sort();
    assert.deepEqual(codes, ["switch_1", "switch_2"]);
    // switch_1 だけ off があるので toggleable、switch_2 は片側のみ
    const row1 = rows.find((r) => r.onAction?.params.switchCode === "switch_1")!;
    const row2 = rows.find((r) => r.onAction?.params.switchCode === "switch_2")!;
    assert.equal(isRowToggleable(row1), true);
    assert.equal(isRowToggleable(row2), false);
  });

  it("treats actions without a value as single-shot rows that are not toggleable", () => {
    const rows = groupActionsIntoRows([
      makeAction("plain", "plug-a", undefined),
    ]);
    assert.equal(rows.length, 1);
    assert.equal(rows[0].onAction?.id, "plain");
    assert.equal(rows[0].offAction, undefined);
    assert.equal(isRowToggleable(rows[0]), false);
  });

  it("keeps rows from different appliances separate", () => {
    const rows = groupActionsIntoRows([
      makeAction("a-on", "plug-a", true),
      makeAction("b-on", "plug-b", true),
      makeAction("a-off", "plug-a", false),
      makeAction("b-off", "plug-b", false),
    ]);
    assert.equal(rows.length, 2);
    for (const row of rows) {
      assert.equal(isRowToggleable(row), true);
    }
  });

  it("falls back to switch when switchCode is empty", () => {
    const rows = groupActionsIntoRows([
      makeAction("on", "plug-a", true, ""),
      makeAction("off", "plug-a", false, ""),
    ]);
    assert.equal(rows.length, 1);
    assert.equal(isRowToggleable(rows[0]), true);
  });
});
