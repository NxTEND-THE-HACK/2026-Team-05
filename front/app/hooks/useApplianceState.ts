import { useQuery } from "@tanstack/react-query";
import { request } from "~/services/backendApiClient";
import { queryKeys } from "./queryKeys";

export interface ApplianceState {
  applianceId: string;
  online: boolean;
  value: boolean | null;
  switchCode: string;
  source: "tuya" | "dry-run" | "no-action" | string;
  error?: string;
  fetchedAt: string;
}

/**
 * 単一 appliance の現在状態をバックエンド経由で取得する。
 * refetchInterval で 30 秒ごとにポーリングし、Tuya 側や物理スイッチの変更を UI へ反映する。
 * dry-run モードでは source="dry-run" + value=null が返る。
 */
export function useApplianceState(applianceId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.applianceState(applianceId ?? "_"),
    enabled: Boolean(applianceId),
    refetchInterval: 30_000,
    staleTime: 10_000,
    queryFn: async () => {
      const data = await request<ApplianceState>(
        `/api/appliances/${encodeURIComponent(applianceId as string)}/state`,
      );
      return data;
    },
  });
}
