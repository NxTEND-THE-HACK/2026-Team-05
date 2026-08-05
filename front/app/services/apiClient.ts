import type {
  Camera,
  Motion,
  Appliance,
  Action,
  MotionBinding,
  ActionLog,
  CreateApplianceRequest,
  CreateActionRequest,
  CreateBindingRequest,
  CamerasResponse,
  MotionsResponse,
  AppliancesResponse,
  ActionsResponse,
  BindingsResponse,
  LogsResponse,
  ExecuteActionResponse,
} from "~/types/api";
import {
  mockCameras,
  mockMotions,
  mockAppliances,
  mockActions,
  mockBindings,
  mockLogs,
} from "~/mocks/data";

// モック用の遅延（200〜500ms）
function delay(min = 200, max = 500): Promise<void> {
  const ms = Math.floor(Math.random() * (max - min + 1)) + min;
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ============================================================
// 読み取り系
// ============================================================

export async function getCameras(): Promise<CamerasResponse> {
  await delay();
  return { cameras: [...mockCameras] };
}

export async function getMotions(): Promise<MotionsResponse> {
  await delay();
  return { motions: [...mockMotions] };
}

export async function getAppliances(): Promise<AppliancesResponse> {
  await delay();
  const appliances = [...mockAppliances];
  return { appliances };
}

/** 指定家電に属する操作一覧を取得 */
export async function getActions(applianceId?: string): Promise<ActionsResponse> {
  await delay();
  const actions = applianceId
    ? mockActions.filter((a) => a.applianceId === applianceId)
    : [...mockActions];
  return { actions };
}

export async function getBindings(): Promise<BindingsResponse> {
  await delay();
  return { bindings: [...mockBindings] };
}

export async function getLogs(): Promise<LogsResponse> {
  await delay();
  return { logs: [...mockLogs] };
}

// ============================================================
// 作成系
// ============================================================

let nextApplianceId = 10;

export async function createAppliance(
  data: CreateApplianceRequest,
): Promise<Appliance> {
  await delay();
  const appliance: Appliance = {
    id: `appliance-${nextApplianceId++}`,
    name: data.name,
    category: data.category,
    createdAt: new Date().toISOString(),
  };
  mockAppliances.push(appliance);
  return appliance;
}

let nextActionId = 20;

export async function createAction(data: CreateActionRequest): Promise<Action> {
  await delay();
  const action: Action = {
    id: `action-${nextActionId++}`,
    applianceId: data.applianceId,
    name: data.name,
    providerType: data.providerType,
    params: { ...data.params },
  };
  mockActions.push(action);
  return action;
}

let nextBindingId = 10;

export async function createBinding(
  data: CreateBindingRequest,
): Promise<MotionBinding> {
  await delay();
  const binding: MotionBinding = {
    id: `binding-${nextBindingId++}`,
    cameraId: data.cameraId,
    motionId: data.motionId,
    actionId: data.actionId,
    isEnabled: true,
    createdAt: new Date().toISOString(),
  };
  mockBindings.push(binding);
  return binding;
}

// ============================================================
// 操作系
// ============================================================

let nextLogId = 20;

/** 手動アクション実行 */
export async function executeAction(
  actionId: string,
): Promise<ExecuteActionResponse> {
  await delay(500, 800);
  const action = mockActions.find((a) => a.id === actionId);
  if (!action) {
    return { success: false, message: "指定された操作が見つかりません" };
  }
  // モック実行ログを追加
  mockLogs.unshift({
    id: `log-${nextLogId++}`,
    eventId: `evt-manual-${Date.now()}`,
    cameraId: "manual",
    motionCode: "MANUAL_TRIGGER",
    actionId: action.id,
    actionName: action.name,
    status: "SUCCESS",
    detectedAt: new Date().toISOString(),
  });
  return { success: true };
}
