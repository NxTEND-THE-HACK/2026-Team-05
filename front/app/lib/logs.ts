import type { ActionLog } from "~/types/backendApi";

export function mergeLogList(
  currentLogs: ActionLog[] | undefined,
  log: ActionLog,
  limit: number,
): ActionLog[] | undefined {
  if (!currentLogs) return undefined;

  return [
    log,
    ...currentLogs.filter((currentLog) => currentLog.id !== log.id),
  ].slice(0, limit);
}
