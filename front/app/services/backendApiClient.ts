/**
 * TEMP_BACKEND_DEMO
 * 仮画面専用のAPIクライアント。削除手順は docs/temporary-backend-demo-ui.md を参照。
 */
import type {
  Action,
  ActionLog,
  Appliance,
  BackendSnapshot,
  Camera,
  CreateBindingRequest,
  ExecuteActionResponse,
  Motion,
  MotionBinding,
} from "~/types/backendApi";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080"
).replace(/\/$/, "");

interface ApiErrorBody {
  error?: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as ApiErrorBody;
      if (body.error) message = body.error;
    } catch {
      // Keep the HTTP status when the response is not JSON.
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

export async function getSnapshot(): Promise<BackendSnapshot> {
  const [cameras, motions, appliances, actions, bindings, logs] =
    await Promise.all([
      request<{ cameras: Camera[] }>("/api/cameras"),
      request<{ motions: Motion[] }>("/api/motions"),
      request<{ appliances: Appliance[] }>("/api/appliances"),
      request<{ actions: Action[] }>("/api/actions"),
      request<{ bindings: MotionBinding[] }>("/api/bindings"),
      request<{ logs: ActionLog[] }>("/api/logs?limit=20"),
    ]);

  return {
    cameras: cameras.cameras,
    motions: motions.motions,
    appliances: appliances.appliances,
    actions: actions.actions,
    bindings: bindings.bindings,
    logs: logs.logs,
  };
}

export function saveBinding(
  input: CreateBindingRequest,
): Promise<MotionBinding> {
  return request<MotionBinding>("/api/bindings", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function executeAction(
  actionId: string,
): Promise<ExecuteActionResponse> {
  return request<ExecuteActionResponse>(`/api/actions/${actionId}/execute`, {
    method: "POST",
  });
}
