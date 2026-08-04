import type { Camera, Motion, Appliance, Action, MotionBinding, ActionLog } from "~/types/api";

// ============================================================
// カメラ（2台）
// ============================================================

export const mockCameras: Camera[] = [
  {
    id: "demo-camera-1",
    name: "リビング用カメラ",
    streamUrl: "http://192.168.1.10:8080/stream",
    location: "リビング",
    isEnabled: true,
    createdAt: "2026-07-20T10:00:00Z",
  },
  {
    id: "demo-camera-2",
    name: "寝室用カメラ",
    streamUrl: "http://192.168.1.11:8080/stream",
    location: "寝室",
    isEnabled: true,
    createdAt: "2026-07-20T10:30:00Z",
  },
];

// ============================================================
// 固定モーション（4種類）
// ============================================================

export const mockMotions: Motion[] = [
  {
    id: "motion-1",
    code: "MOTION_RAISE_RIGHT_HAND",
    name: "右手上げ",
    description: "右手を肩より上に上げるジェスチャー",
  },
  {
    id: "motion-2",
    code: "MOTION_RAISE_LEFT_HAND",
    name: "左手上げ",
    description: "左手を肩より上に上げるジェスチャー",
  },
  {
    id: "motion-3",
    code: "MOTION_BOTH_HANDS_UP",
    name: "両手上げ",
    description: "両手を同時に肩より上に上げるジェスチャー",
  },
  {
    id: "motion-4",
    code: "MOTION_WAVE_HANDS",
    name: "手を振る",
    description: "手を左右に振るジェスチャー",
  },
];

// ============================================================
// 家電（3台）
// ============================================================

export const mockAppliances: Appliance[] = [
  {
    id: "appliance-1",
    name: "リビング照明",
    category: "照明",
    createdAt: "2026-07-25T09:00:00Z",
  },
  {
    id: "appliance-2",
    name: "リビングエアコン",
    category: "エアコン",
    createdAt: "2026-07-25T09:15:00Z",
  },
  {
    id: "appliance-3",
    name: "寝室扇風機",
    category: "扇風機",
    createdAt: "2026-07-25T09:30:00Z",
  },
];

// ============================================================
// 家電操作（家電ごとに操作を定義）
// ============================================================

export const mockActions: Action[] = [
  // リビング照明
  {
    id: "action-1",
    applianceId: "appliance-1",
    name: "照明オン",
    providerType: "IR_DEVICE",
    params: { command: "power_on" },
  },
  {
    id: "action-2",
    applianceId: "appliance-1",
    name: "照明オフ",
    providerType: "IR_DEVICE",
    params: { command: "power_off" },
  },
  // リビングエアコン
  {
    id: "action-3",
    applianceId: "appliance-2",
    name: "冷房オン（24℃）",
    providerType: "IR_DEVICE",
    params: { command: "cool_on", temperature: 24 },
  },
  {
    id: "action-4",
    applianceId: "appliance-2",
    name: "暖房オン（22℃）",
    providerType: "IR_DEVICE",
    params: { command: "heat_on", temperature: 22 },
  },
  {
    id: "action-5",
    applianceId: "appliance-2",
    name: "エアコンオフ",
    providerType: "IR_DEVICE",
    params: { command: "power_off" },
  },
  // 寝室扇風機
  {
    id: "action-6",
    applianceId: "appliance-3",
    name: "首振りオン",
    providerType: "IR_DEVICE",
    params: { command: "swing_on" },
  },
  {
    id: "action-7",
    applianceId: "appliance-3",
    name: "首振りオフ",
    providerType: "IR_DEVICE",
    params: { command: "swing_off" },
  },
];

// ============================================================
// 紐付け設定（3件）
// ============================================================

export const mockBindings: MotionBinding[] = [
  {
    id: "binding-1",
    cameraId: "demo-camera-1",
    motionId: "motion-1",
    actionId: "action-1",
    isEnabled: true,
    createdAt: "2026-07-26T12:00:00Z",
  },
  {
    id: "binding-2",
    cameraId: "demo-camera-1",
    motionId: "motion-3",
    actionId: "action-3",
    isEnabled: true,
    createdAt: "2026-07-26T12:15:00Z",
  },
  {
    id: "binding-3",
    cameraId: "demo-camera-2",
    motionId: "motion-4",
    actionId: "action-6",
    isEnabled: true,
    createdAt: "2026-07-26T12:30:00Z",
  },
];

// ============================================================
// 操作ログ（5件）
// ============================================================

export const mockLogs: ActionLog[] = [
  {
    id: "log-1",
    eventId: "evt-20260804-001",
    cameraId: "demo-camera-1",
    cameraName: "リビング用カメラ",
    motionCode: "MOTION_RAISE_RIGHT_HAND",
    motionName: "右手上げ",
    actionId: "action-1",
    actionName: "照明オン",
    status: "SUCCESS",
    detectedAt: "2026-08-04T18:30:15Z",
  },
  {
    id: "log-2",
    eventId: "evt-20260804-002",
    cameraId: "demo-camera-1",
    cameraName: "リビング用カメラ",
    motionCode: "MOTION_BOTH_HANDS_UP",
    motionName: "両手上げ",
    actionId: "action-3",
    actionName: "冷房オン（24℃）",
    status: "SUCCESS",
    detectedAt: "2026-08-04T18:32:40Z",
  },
  {
    id: "log-3",
    eventId: "evt-20260804-003",
    cameraId: "demo-camera-2",
    cameraName: "寝室用カメラ",
    motionCode: "MOTION_WAVE_HANDS",
    motionName: "手を振る",
    actionId: "action-6",
    actionName: "首振りオン",
    status: "SUCCESS",
    detectedAt: "2026-08-04T18:35:02Z",
  },
  {
    id: "log-4",
    eventId: "evt-20260804-004",
    cameraId: "demo-camera-1",
    cameraName: "リビング用カメラ",
    motionCode: "MOTION_RAISE_RIGHT_HAND",
    motionName: "右手上げ",
    status: "COOLING_DOWN",
    detectedAt: "2026-08-04T18:36:10Z",
  },
  {
    id: "log-5",
    eventId: "evt-20260804-005",
    cameraId: "demo-camera-1",
    cameraName: "リビング用カメラ",
    motionCode: "MOTION_RAISE_LEFT_HAND",
    motionName: "左手上げ",
    status: "FAILED",
    errorMessage: "紐付け設定が見つかりません",
    detectedAt: "2026-08-04T18:38:55Z",
  },
];
