// ============================================================
// ドメインモデル型定義
// ============================================================

/** カメラ */
export interface Camera {
  id: string;
  name: string;
  streamUrl: string;
  location: string;
  isEnabled: boolean;
  createdAt: string;
}

/** 固定モーション（認識するジェスチャーの定義） */
export interface Motion {
  id: string;
  /** 例: "MOTION_RAISE_RIGHT_HAND", "MOTION_WAVE_HANDS" */
  code: string;
  /** 例: "右手上げ", "両手振る" */
  name: string;
  description: string;
}

/** 家電 */
export interface Appliance {
  id: string;
  name: string;
  /** 例: "照明", "エアコン", "扇風機" */
  category: string;
  createdAt: string;
}

/** 家電操作のプロバイダ種別 */
export type ActionProviderType = "IR_DEVICE" | "GENERIC_HTTP" | "NATURE_REMO";

/** 家電操作 */
export interface Action {
  id: string;
  applianceId: string;
  name: string;
  providerType: ActionProviderType;
  /** 呼び出しパラメータ（プロバイダに依存） */
  params: Record<string, unknown>;
}

/** 紐付け設定（カメラ × モーション × 操作 の組み合わせ） */
export interface MotionBinding {
  id: string;
  cameraId: string;
  motionId: string;
  actionId: string;
  isEnabled: boolean;
  createdAt: string;
}

/** 操作ログのステータス */
export type ActionLogStatus = "SUCCESS" | "FAILED" | "COOLING_DOWN";

/** 操作ログ */
export interface ActionLog {
  id: string;
  eventId: string;
  cameraId: string;
  cameraName?: string;
  motionCode: string;
  motionName?: string;
  actionId: string;
  actionName?: string;
  status: ActionLogStatus;
  errorMessage?: string;
  detectedAt: string;
}

// ============================================================
// API リクエスト型
// ============================================================

export interface CreateApplianceRequest {
  name: string;
  category: string;
}

export interface CreateActionRequest {
  applianceId: string;
  name: string;
  providerType: ActionProviderType;
  params: Record<string, unknown>;
}

export interface CreateBindingRequest {
  cameraId: string;
  motionId: string;
  actionId: string;
}

// ============================================================
// API レスポンス型（単一・リスト取得）
// ============================================================

export interface CameraResponse {
  camera: Camera;
}

export interface CamerasResponse {
  cameras: Camera[];
}

export interface MotionResponse {
  motion: Motion;
}

export interface MotionsResponse {
  motions: Motion[];
}

export interface ApplianceResponse {
  appliance: Appliance;
}

export interface AppliancesResponse {
  appliances: Appliance[];
}

export interface ActionResponse {
  action: Action;
}

export interface ActionsResponse {
  actions: Action[];
}

export interface BindingResponse {
  binding: MotionBinding;
}

export interface BindingsResponse {
  bindings: MotionBinding[];
}

export interface LogsResponse {
  logs: ActionLog[];
}

/** 手動実行のレスポンス */
export interface ExecuteActionResponse {
  success: boolean;
  message?: string;
}
