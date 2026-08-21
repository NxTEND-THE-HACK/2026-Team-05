import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Appliance, CreateApplianceRequest } from "~/types/backendApi";
import { createAppliance, request } from "~/services/backendApiClient";
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

export function useCreateAppliance() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateApplianceRequest) => createAppliance(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.appliances });
    },
  });
}
