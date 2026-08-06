import { useQuery } from "@tanstack/react-query";
import { getApiBaseUrl } from "~/services/backendApiClient";
import { queryKeys } from "./queryKeys";

export function useApiHealth() {
  const apiBaseUrl = getApiBaseUrl();

  return useQuery({
    queryKey: queryKeys.health,
    queryFn: async () => {
      const res = await fetch(`${apiBaseUrl}/healthz`);
      if (!res.ok) throw new Error("API unavailable");
      return res.json() as Promise<{ status: string }>;
    },
    refetchInterval: 10_000,
    retry: 1,
  });
}
