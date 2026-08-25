import type { TuyaAction } from "~/types/backendApi";

export interface ControlRow {
  key: string;
  name: string;
  onAction?: TuyaAction;
  offAction?: TuyaAction;
}

/**
 * Action の行キー。同一 appliance でも switchCode が異なれば別行として扱う。
 * 同じ appliance 内で value=true / value=false の Action が揃っているときだけ
 * トグル UI として使える。それ以外は disable して単発実行に留める。
 */
function rowKey(action: TuyaAction): string {
  const code = action.params.switchCode?.trim() || "switch";
  return `${action.applianceId}::${code}`;
}

/** 行キーから人間に見やすい名前を引く。Action 名から "ON"/"OFF" サフィックスを剥がす。 */
function deriveRowName(actions: TuyaAction[]): string {
  const seed = actions[0];
  return (
    seed.name.replace(/\s*(ON|OFF|オン|オフ)\s*$/i, "").trim() || seed.name
  );
}

/**
 * Action の配列をトグル UI の行データに変換する。
 * 同じ (applianceId, switchCode) ペアで value=true と value=false の Action が
 * 揃った行だけをトグル行として返す。片側しか無い Action も同じ行にまとめず、
 * 単発実行行として別キーで返す (UI 側で disable にして安全側に倒す)。
 */
export function groupActionsIntoRows(actions: TuyaAction[]): ControlRow[] {
  // まず (applianceId, switchCode) ごとに Action をまとめて、value の有無ごとに分類。
  const groups = new Map<
    string,
    { onAction?: TuyaAction; offAction?: TuyaAction; any: TuyaAction }
  >();
  for (const a of actions) {
    const key = rowKey(a);
    const bucket = groups.get(key) ?? { any: a };
    if (a.params.value === true) bucket.onAction = a;
    else if (a.params.value === false) bucket.offAction = a;
    else {
      // value 未知の Action は on 側に仮置きせず、独立した単発行として扱う。
      // key を分離することで disable な Switch として表示される。
      const fallbackKey = `${key}::fallback-${a.id}`;
      groups.set(fallbackKey, { onAction: a, any: a });
      continue;
    }
    groups.set(key, bucket);
  }

  const rows: ControlRow[] = [];
  for (const [key, bucket] of groups) {
    rows.push({
      key,
      name: deriveRowName([bucket.onAction, bucket.offAction, bucket.any].filter(Boolean) as TuyaAction[]),
      onAction: bucket.onAction,
      offAction: bucket.offAction,
    });
  }
  return rows;
}

/** 行がトグル可能 (両方向の Action がある) かを返す。 */
export function isRowToggleable(row: ControlRow): boolean {
  return Boolean(row.onAction && row.offAction);
}
