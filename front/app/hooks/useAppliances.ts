import { useQuery } from "@tanstack/react-query";
import type { Appliance } from "~/types/backendApi";
import { request } from "~/services/backendApiClient";
import { queryKeys } from "./queryKeys";

export function useAppliances() {
  return useQuery({
    queryKey: queryKeys.appliances,
    queryFn: async () => {
      const data = await request<{ appliances: Appliance[] }>("/api/appliances");
      return data.appliances;
    },
  });
}
