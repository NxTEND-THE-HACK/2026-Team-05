import { useQuery } from "@tanstack/react-query";
import type { Action } from "~/types/backendApi";
import { request } from "~/services/backendApiClient";
import { queryKeys } from "./queryKeys";

export function useActions(applianceId?: string) {
  return useQuery({
    queryKey: queryKeys.actions(applianceId),
    queryFn: async () => {
      const url = applianceId
        ? `/api/actions?applianceId=${encodeURIComponent(applianceId)}`
        : "/api/actions";
      const data = await request<{ actions: Action[] }>(url);
      return data.actions;
    },
  });
}
