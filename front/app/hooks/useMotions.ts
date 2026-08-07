import { useQuery } from "@tanstack/react-query";
import type { Motion } from "~/types/backendApi";
import { request } from "~/services/backendApiClient";
import { queryKeys } from "./queryKeys";

export function useMotions() {
  return useQuery({
    queryKey: queryKeys.motions,
    queryFn: async () => {
      const data = await request<{ motions: Motion[] }>("/api/motions");
      return data.motions;
    },
    staleTime: 5 * 60_000,
  });
}
