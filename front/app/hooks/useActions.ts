import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Action, CreateActionRequest } from "~/types/backendApi";
import { createAction, deleteAction, request } from "~/services/backendApiClient";
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

export function useCreateAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateActionRequest) => createAction(input),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.actions(variables.applianceId),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.actions() });
    },
  });
}

export function useDeleteAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ actionId }: { actionId: string; applianceId: string }) =>
      deleteAction(actionId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.actions(variables.applianceId),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.actions() });
      queryClient.invalidateQueries({ queryKey: queryKeys.bindings });
    },
  });
}
