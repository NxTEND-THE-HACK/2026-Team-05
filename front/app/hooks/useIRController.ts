import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  ConfirmIRLearnRequest,
  IRControllerHealth,
} from "~/types/backendApi";
import {
  confirmIRLearning,
  getIRHealth,
  startIRLearning,
  stopIRLearning,
  testIR,
} from "~/services/backendApiClient";
import { queryKeys } from "./queryKeys";

export function useIRHealth(applianceId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.irHealth(applianceId ?? "_"),
    enabled: Boolean(applianceId),
    refetchInterval: 5_000,
    retry: 1,
    queryFn: async () => {
      const data = await getIRHealth(applianceId as string);
      return data as IRControllerHealth;
    },
  });
}

export function useStartIRLearning() {
  return useMutation({
    mutationFn: ({
      applianceId,
      timeoutSeconds,
    }: {
      applianceId: string;
      timeoutSeconds?: number;
    }) => startIRLearning(applianceId, timeoutSeconds),
  });
}

export function useConfirmIRLearning() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      applianceId,
      input,
    }: {
      applianceId: string;
      input: ConfirmIRLearnRequest;
    }) => confirmIRLearning(applianceId, input),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.actions(variables.applianceId),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.actions() });
    },
  });
}

export function useStopIRLearning() {
  return useMutation({
    mutationFn: ({
      applianceId,
      sessionId,
    }: {
      applianceId: string;
      sessionId: string;
    }) => stopIRLearning(applianceId, sessionId),
  });
}

export function useTestIR() {
  return useMutation({
    mutationFn: (applianceId: string) => testIR(applianceId),
  });
}
