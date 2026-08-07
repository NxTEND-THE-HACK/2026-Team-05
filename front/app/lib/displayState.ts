/**
 * optimisticState と applianceState の優先順位解決ヘルパ。
 *
 * レース条件:
 *   - ユーザが ON を押下 → setOptimisticState({ key: true }) で即時 ON 表示
 *   - invalidateQueries が走る → Tuya Cloud が押下前の古い値 false を返すことがある
 *   - dataUpdatedAt 変化 → ここで楽観をクリアすると UI が先祖返りする
 *
 * 方針:
 *   - 楽観値と実機値が一致したら楽観をクリア
 *   - 一致しない間は楽観を優先 (Tuya 反映遅延 / 物理操作の可能性)
 */

import type { ApplianceSwitchState } from "~/hooks/useApplianceState";

export interface ResolveInput {
  optimistic: boolean | undefined;
  rowState: ApplianceSwitchState | undefined;
}

/**
 * 1 行分の表示状態を決定する。
 * 優先順位: optimistic → rowState.value → "unknown"
 */
export function resolveDisplayStateValue(input: ResolveInput): boolean | "unknown" {
  if (input.optimistic !== undefined) return input.optimistic;
  if (input.rowState?.value !== null && input.rowState?.value !== undefined) {
    return input.rowState.value;
  }
  return "unknown";
}

/**
 * optimisticState のうち「実機状態が追いついたエントリだけ」を除外した新しい map を返す。
 * 副作用なしの pure 関数。React の setState 内で利用する。
 *
 * 入力:
 *   prev:   現在の楽観状態
 *   values: 実機から返ってきた最新値 (undefined = 未取得)
 *
 * ロジック:
 *   - 実機値が undefined (まだ API から来ていない) → 楽観を維持
 *   - 実機値が楽観値と一致している (Tuya 反映完了) → 楽観をクリア
 *   - 実機値が楽観値と異なる (古い値 or 物理操作) → 楽観を維持
 *     こうすることで invalidateQueries の直後に古い値が来ても UI が先祖返りしない。
 */
export function reconcileOptimisticState(
  prev: Record<string, boolean>,
  values: Record<string, boolean | undefined>,
): Record<string, boolean> {
  const next: Record<string, boolean> = {};
  for (const [key, optimistic] of Object.entries(prev)) {
    const actual = values[key];
    if (actual === undefined) {
      // まだ実機値が無い (null や未取得) → 楽観を維持
      next[key] = optimistic;
      continue;
    }
    if (actual === optimistic) {
      // 実機が楽観値に追いついた → 楽観をクリア (= このエントリを next に入れない)
      continue;
    }
    // 実機値が楽観値と異なる (古い or 物理操作) → 楽観を維持
    next[key] = optimistic;
  }
  return next;
}
