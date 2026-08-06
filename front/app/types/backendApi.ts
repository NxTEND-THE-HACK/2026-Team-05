/**
 * バックエンドAPI型定義。
 */

export interface Camera {
  id: string;
  name: string;
  streamUrl: string;
  location: string;
  isEnabled: boolean;
  createdAt: string;
}

export interface Motion {
  id: string;
  code: string;
  name: string;
  description: string;
}

export interface Appliance {
  id: string;
  name: string;
  category: string;
  createdAt: string;
}

export interface Action {
  id: string;
  applianceId: string;
  name: string;
  providerType: "TUYA";
  params: {
    deviceId?: string;
    deviceIdEnv?: "PLUG_A_ID" | "PLUG_B_ID" | "PLUG_C_ID";
    switchCode?: string;
    value: boolean;
  };
}

export interface MotionBinding {
  id: string;
  cameraId?: string;
  motionId: string;
  actionId: string;
  isEnabled: boolean;
  createdAt: string;
}

export type ActionLogStatus = "SUCCESS" | "FAILED" | "COOLING_DOWN";

export interface ActionLog {
  id: string;
  eventId: string;
  cameraId: string;
  cameraName?: string;
  motionCode: string;
  motionName?: string;
  actionId?: string;
  actionName?: string;
  status: ActionLogStatus;
  errorMessage?: string;
  detectedAt: string;
}

export interface CreateBindingRequest {
  cameraId?: string;
  motionId: string;
  actionId: string;
}

export interface ExecuteActionResponse {
  success: boolean;
  message?: string;
}

export interface BackendSnapshot {
  cameras: Camera[];
  motions: Motion[];
  appliances: Appliance[];
  actions: Action[];
  bindings: MotionBinding[];
  logs: ActionLog[];
}
