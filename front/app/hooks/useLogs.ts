import { useEffect } from "react";
import {
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import type { ActionLog } from "~/types/backendApi";
import { getApiBaseUrl, request } from "~/services/backendApiClient";
import { queryKeys } from "./queryKeys";

interface LogStream {
  source: EventSource;
  references: number;
  onConnected: () => void;
  onLog: (event: Event) => void;
}

const logStreams = new WeakMap<QueryClient, LogStream>();

function updateLogQueries(queryClient: QueryClient, log: ActionLog) {
  for (const [queryKey, currentLogs] of queryClient.getQueriesData<
    ActionLog[]
  >({ queryKey: ["logs"] })) {
    if (!currentLogs) continue;
    const rawLimit = queryKey[1];
    const limit = typeof rawLimit === "number" && rawLimit > 0 ? rawLimit : 100;
    const nextLogs = [
      log,
      ...currentLogs.filter((currentLog) => currentLog.id !== log.id),
    ];
    queryClient.setQueryData<ActionLog[]>(queryKey, nextLogs.slice(0, limit));
  }
}

function acquireLogStream(queryClient: QueryClient) {
  let stream = logStreams.get(queryClient);
  if (!stream) {
    const source = new EventSource(`${getApiBaseUrl()}/api/logs/stream`);
    const onConnected = () => {
      // Reconcile logs once after each connection or reconnect.
      void queryClient.invalidateQueries({ queryKey: ["logs"] });
    };
    const onLog = (event: Event) => {
      try {
        const log = JSON.parse((event as MessageEvent<string>).data) as ActionLog;
        updateLogQueries(queryClient, log);
      } catch {
        // The regular query refresh remains the fallback for malformed events.
      }
    };
    source.addEventListener("connected", onConnected);
    source.addEventListener("log", onLog);
    stream = { source, references: 0, onConnected, onLog };
    logStreams.set(queryClient, stream);
  }

  stream.references += 1;
  return () => {
    const activeStream = logStreams.get(queryClient);
    if (!activeStream) return;
    activeStream.references -= 1;
    if (activeStream.references > 0) return;
    activeStream.source.removeEventListener("connected", activeStream.onConnected);
    activeStream.source.removeEventListener("log", activeStream.onLog);
    activeStream.source.close();
    logStreams.delete(queryClient);
  };
}

export function useLogs(limit = 100) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }
    return acquireLogStream(queryClient);
  }, [queryClient]);

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
