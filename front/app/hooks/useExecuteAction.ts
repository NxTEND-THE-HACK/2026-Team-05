import { useMutation, useQueryClient } from "@tanstack/react-query";
import { executeAction } from "~/services/backendApiClient";

export function useExecuteAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (actionId: string) => executeAction(actionId),
    onSuccess: () => {
      // Execution results are recorded as action logs.
      queryClient.invalidateQueries({ queryKey: ["logs"] });
    },
  });
}
