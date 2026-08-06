import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { MotionBinding, CreateBindingRequest } from "~/types/backendApi";
import { request } from "~/services/backendApiClient";
import { queryKeys } from "./queryKeys";

export function useBindings() {
  return useQuery({
    queryKey: queryKeys.bindings,
    queryFn: async () => {
      const data = await request<{ bindings: MotionBinding[] }>("/api/bindings");
      return data.bindings;
    },
  });
}

export function useCreateBinding() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateBindingRequest) =>
      request<MotionBinding>("/api/bindings", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bindings });
    },
  });
}
