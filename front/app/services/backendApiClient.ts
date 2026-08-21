/**
 * バックエンドAPIクライアント。
 */

import type {
  Action,
  ActionLog,
  Appliance,
  BackendSnapshot,
  Camera,
  ConfirmIRLearnRequest,
  CreateActionRequest,
  CreateApplianceRequest,
  CreateBindingRequest,
  ExecuteActionResponse,
  IRControllerHealth,
  IRLearningSession,
  Motion,
  MotionBinding,
} from "~/types/backendApi";

const API_BASE_URL = (
  import.meta.env?.VITE_API_BASE_URL ?? "http://localhost:8080"
).replace(/\/$/, "");

interface ApiErrorBody {
  error?: string;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
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

  if (response.status === 204) {
    return undefined as T;
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

export function createAppliance(
  input: CreateApplianceRequest,
): Promise<Appliance> {
  return request<Appliance>("/api/appliances", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function createAction(input: CreateActionRequest): Promise<Action> {
  return request<Action>("/api/actions", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function saveBinding(
  input: CreateBindingRequest,
): Promise<MotionBinding> {
  return request<MotionBinding>("/api/bindings", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function deleteBinding(bindingId: string): Promise<void> {
  return request<void>(`/api/bindings/${encodeURIComponent(bindingId)}`, {
    method: "DELETE",
  });
}

export function executeAction(
  actionId: string,
): Promise<ExecuteActionResponse> {
  return request<ExecuteActionResponse>(`/api/actions/${actionId}/execute`, {
    method: "POST",
  });
}

export function getIRHealth(
  applianceId: string,
): Promise<IRControllerHealth> {
  return request<IRControllerHealth>(
    `/api/appliances/${encodeURIComponent(applianceId)}/ir/health`,
  );
}

export function startIRLearning(
  applianceId: string,
  timeoutSeconds?: number,
): Promise<IRLearningSession> {
  return request<IRLearningSession>(
    `/api/appliances/${encodeURIComponent(applianceId)}/ir/learn/start`,
    {
      method: "POST",
      body: JSON.stringify({ timeoutSeconds }),
    },
  );
}

export function getIRLearningStatus(
  applianceId: string,
): Promise<IRLearningSession> {
  return request<IRLearningSession>(
    `/api/appliances/${encodeURIComponent(applianceId)}/ir/learn/status`,
  );
}

export function confirmIRLearning(
  applianceId: string,
  input: ConfirmIRLearnRequest,
): Promise<Action> {
  return request<Action>(
    `/api/appliances/${encodeURIComponent(applianceId)}/ir/learn/confirm`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}

export function stopIRLearning(
  applianceId: string,
  sessionId: string,
): Promise<{ ok: boolean; state: string }> {
  return request<{ ok: boolean; state: string }>(
    `/api/appliances/${encodeURIComponent(applianceId)}/ir/learn/stop`,
    {
      method: "POST",
      body: JSON.stringify({ sessionId }),
    },
  );
}

export function testIR(applianceId: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(
    `/api/appliances/${encodeURIComponent(applianceId)}/ir/test`,
    {
      method: "POST",
      body: JSON.stringify({}),
    },
  );
}
