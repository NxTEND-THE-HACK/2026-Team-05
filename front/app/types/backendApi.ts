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

export type ControlProvider = "TUYA" | "ESP32_IR";

export interface Appliance {
  id: string;
  name: string;
  category: string;
  controlProvider: ControlProvider;
  controllerId?: string;
  createdAt: string;
}

export interface IRSignal {
  protocol: string;
  bits?: number;
  code?: string;
  address?: string;
  command?: string;
  raw?: number[];
  carrierHz: number;
}

export interface TuyaActionParams {
  deviceId?: string;
  deviceIdEnv?: string;
  switchCode?: string;
  value?: boolean;
}

export interface IRActionParams {
  controllerId: string;
  signal: IRSignal;
  repeat: number;
}

export interface TuyaAction {
  id: string;
  applianceId: string;
  name: string;
  providerType: "TUYA";
  params: TuyaActionParams;
}

export interface IRAction {
  id: string;
  applianceId: string;
  name: string;
  providerType: "ESP32_IR";
  params: IRActionParams;
}

export type Action = TuyaAction | IRAction;

export function isTuyaAction(action: Action): action is TuyaAction {
  return action.providerType === "TUYA";
}

export function isIRAction(action: Action): action is IRAction {
  return action.providerType === "ESP32_IR";
}

export interface IRLearnCapture {
  captureId: string;
  isRepeat: boolean;
  signal: IRSignal;
}

export interface IRLearningSession {
  sessionId: string;
  applianceId: string;
  controllerId: string;
  state: "learning" | "captured" | string;
  expiresAt: string;
  capture?: IRLearnCapture;
}

export interface IRControllerHealth {
  ok: boolean;
  controllerId?: string;
  state: "idle" | "learning" | "sending" | "error" | string;
  wifiConnected: boolean;
  rssi?: number;
  ip?: string;
  firmwareVersion?: string;
  message?: string;
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

export interface CreateApplianceRequest {
  name: string;
  category: string;
  controlProvider?: ControlProvider;
  controllerId?: string;
}

export interface CreateActionRequest {
  applianceId: string;
  name: string;
  providerType: "TUYA";
  params: TuyaActionParams;
}

export interface ConfirmIRLearnRequest {
  sessionId: string;
  captureId: string;
  name: string;
  repeat?: number;
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
