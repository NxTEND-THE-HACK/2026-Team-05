import { useQuery } from "@tanstack/react-query";
import type { ActionLog } from "~/types/backendApi";
import { request } from "~/services/backendApiClient";
import { queryKeys } from "./queryKeys";

export function useLogs(limit = 100) {
  return useQuery({
    queryKey: queryKeys.logs(limit),
    queryFn: async () => {
      const data = await request<{ logs: ActionLog[] }>(
        `/api/logs?limit=${limit}`,
      );
      return data.logs;
    },
    refetchInterval: 30_000,
  });
}
