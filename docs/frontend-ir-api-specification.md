# フロントエンド向け ESP32赤外線連携仕様

| 項目 | 内容 |
|---|---|
| 対象 | Reactフロントエンド担当者 |
| バックエンド | Go / Echo |
| APIバージョン | v0.2.0 |
| 最終更新日 | 2026-08-21 |
| OpenAPI | `backend/openapi.yaml` |

## 1. 概要

既存のTuyaスマートプラグに加えて、ESP32赤外線コントローラーで操作する家電を登録できる。

フロントエンドはESP32を直接呼び出さない。すべてGoバックエンドの `/api/*` を呼び出す。ESP32のURLとAPIキーはバックエンドだけが保持する。

API v0.2.0ではバックエンド1インスタンスにつきESP32コントローラー1台を設定する。画面から任意のコントローラーURLやAPIキーを登録する機能はない。

```text
Reactフロント
    │ HTTP/JSON
    ▼
Goバックエンド
    │ X-API-Key付きHTTP
    ▼
ESP32赤外線コントローラー
```

## 2. 既存Tuya画面との分離

`Appliance.controlProvider` でManual Controlを分岐する。

| `controlProvider` | 表示するコントロール |
|---|---|
| `TUYA` | 現在のON/OFF Switch UI |
| `ESP32_IR` | 登録済み赤外線ボタンと「ボタンを登録」UI |

赤外線Actionを既存の `groupActionsIntoRows` に渡さない。赤外線Actionは `value` や `switchCode` を持たないため、既存ロジックでは無効なSwitchになる。

推奨コンポーネント構成:

```text
DeviceDetailPage
├─ TuyaManualControl         controlProvider=TUYA
└─ IRRemoteManualControl     controlProvider=ESP32_IR
   ├─ IRControllerStatus
   ├─ IRActionButtonGrid
   └─ IRLearnActionModal
```

## 3. TypeScript型

```ts
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

export interface TuyaAction {
  id: string;
  applianceId: string;
  name: string;
  providerType: "TUYA";
  params: {
    deviceId?: string;
    deviceIdEnv?: string;
    switchCode?: string;
    value: boolean;
  };
}

export interface IRAction {
  id: string;
  applianceId: string;
  name: string;
  providerType: "ESP32_IR";
  params: {
    controllerId: string;
    signal: IRSignal;
    repeat: number;
  };
}

export type Action = TuyaAction | IRAction;

export interface IRLearnCapture {
  captureId: string;
  isRepeat: boolean;
  signal: IRSignal;
}

export interface IRLearningSession {
  sessionId: string;
  applianceId: string;
  controllerId: string;
  state: "learning" | "captured";
  expiresAt: string;
  capture?: IRLearnCapture;
}
```

`Action` は `providerType` を判別キーにしたdiscriminated unionとして扱う。

## 4. 赤外線デバイスの追加

### リクエスト

```http
POST /api/appliances
Content-Type: application/json
```

```json
{
  "name": "リビング照明",
  "category": "照明",
  "controlProvider": "ESP32_IR"
}
```

`controllerId` は省略可能。省略時はバックエンド設定 `IR_CONTROLLER_ID` が使用される。

### レスポンス `201 Created`

```json
{
  "id": "appliance-...",
  "name": "リビング照明",
  "category": "照明",
  "controlProvider": "ESP32_IR",
  "controllerId": "main-ir",
  "createdAt": "2026-08-21T03:00:00Z"
}
```

既存フロントとの後方互換のため、`controlProvider` を省略した作成リクエストは `TUYA` として扱われる。赤外線デバイスの追加画面では必ず `ESP32_IR` を明示する。

作成成功後にinvalidateするクエリ:

- appliances
- sidebarで使用するappliances
- dashboard snapshot

作成後は `/devices/{id}` へ遷移する。

## 5. コントローラー状態

```http
GET /api/appliances/{applianceId}/ir/health
```

```json
{
  "ok": true,
  "controllerId": "main-ir",
  "state": "idle",
  "wifiConnected": true,
  "rssi": -52,
  "ip": "192.168.1.50",
  "firmwareVersion": "1.2.0"
}
```

`state` は `idle | learning | sending | error`。

赤外線は一方向通信なので、照明の実際のON/OFF状態は取得できない。画面には次を分けて表示する。

- ESP32接続状態: オンライン / オフライン
- 家電状態: 不明
- 最終操作: 操作ログから表示

既存 `GET /api/appliances/{id}/state` を赤外線デバイスに使用した場合、`source="esp32-ir"`, `value=null` になる。

## 6. 学習・登録フロー

### 6.1 学習開始

```http
POST /api/appliances/{applianceId}/ir/learn/start
Content-Type: application/json
```

既定タイムアウトを使う場合:

```json
{}
```

任意指定する場合は5〜120秒:

```json
{
  "timeoutSeconds": 30
}
```

レスポンス `200 OK`:

```json
{
  "sessionId": "ir-learn-...",
  "applianceId": "appliance-...",
  "controllerId": "main-ir",
  "state": "learning",
  "expiresAt": "2026-08-21T03:00:30Z"
}
```

`sessionId` はModal内に保持する。別のデバイスまたはタブですでに学習中の場合は `409 Conflict`。

### 6.2 状態ポーリング

```http
GET /api/appliances/{applianceId}/ir/learn/status
```

500〜1000ms間隔でポーリングする。

受信待ち:

```json
{
  "sessionId": "ir-learn-...",
  "applianceId": "appliance-...",
  "controllerId": "main-ir",
  "state": "learning",
  "expiresAt": "2026-08-21T03:00:30Z"
}
```

受信完了:

```json
{
  "sessionId": "ir-learn-...",
  "applianceId": "appliance-...",
  "controllerId": "main-ir",
  "state": "captured",
  "expiresAt": "2026-08-21T03:00:30Z",
  "capture": {
    "captureId": "capture-42",
    "isRepeat": false,
    "signal": {
      "protocol": "NEC",
      "bits": 32,
      "code": "0x00FF18E7",
      "address": "0x00FF",
      "command": "0x18",
      "raw": [9000, 4500, 560, 560],
      "carrierHz": 38000
    }
  }
}
```

`captured` を受け取ったらポーリングを停止し、機能名入力フォームへ進む。この時点でバックエンドはESP32の学習モードを停止済み。

Rawデータは通常画面に表示せず、詳細の折りたたみ内に表示する。

### 6.3 名前を付けて保存

```http
POST /api/appliances/{applianceId}/ir/learn/confirm
Content-Type: application/json
```

```json
{
  "sessionId": "ir-learn-...",
  "captureId": "capture-42",
  "name": "赤",
  "repeat": 1
}
```

- `name`: 1〜100文字
- `repeat`: 省略時1、指定時1〜5
- 同じデバイス内で同名Actionがある場合は `409 Conflict`
- `sessionId` または `captureId` が古い場合は `404` または `409`

レスポンス `201 Created` は通常の `Action`。成功後、actionsクエリをinvalidateするとManual Controlへボタンが追加される。

### 6.4 キャンセル

Modalを閉じる前に必ず呼び出す。

```http
POST /api/appliances/{applianceId}/ir/learn/stop
Content-Type: application/json
```

```json
{
  "sessionId": "ir-learn-..."
}
```

レスポンス:

```json
{
  "ok": true,
  "state": "idle"
}
```

ブラウザ終了などでstopを呼べない場合も、ESP32とバックエンド側のタイムアウトで学習状態は解除される。

## 7. 登録済みボタンの実行

既存APIをそのまま使用する。

```http
POST /api/actions/{actionId}/execute
```

```json
{
  "success": true
}
```

学習中は送信できず `409 Conflict` になる。競合した操作も操作ログへFAILEDとして保存される。Manual Controlでは学習中のすべての赤外線ボタンをdisabledにする。

赤外線Actionは既存のモーションバインディングでも選択できる。認識イベントから実行された場合も同じExecutorと操作ログを使用する。

## 8. 赤外線LEDテスト

```http
POST /api/appliances/{applianceId}/ir/test
```

```json
{
  "ok": true
}
```

学習中は `409 Conflict`。スマートフォンカメラで赤外線LEDの発光確認を案内する。

## 9. エラー

バックエンドのエラー形式は既存仕様と同じ。

```json
{
  "error": "infrared learning is already in progress"
}
```

| Status | 主な意味 | UIの扱い |
|---:|---|---|
| `400` | デバイス種別・入力値が不正 | 入力エラー表示 |
| `404` | デバイスまたは学習セッションがない | Modalを閉じて再開始 |
| `408` | 学習タイムアウト | 再試行ボタン表示 |
| `409` | 学習競合、未受信、同名Action | 理由を表示して操作を継続 |
| `502` | ESP32が不正応答 | コントローラー障害表示 |
| `503` | ESP32が未設定 | 管理者向け設定エラー表示 |
| `504` | ESP32通信タイムアウト | 再試行表示 |

## 10. UI受け入れ条件

- 既存Tuyaデバイスでは現在のSwitch UIが変化しない
- `ESP32_IR` デバイスだけに赤外線ボタン登録の `＋` が表示される
- Device追加後にサイドバーへ表示され、詳細画面へ遷移する
- 学習開始後に待機、受信、名前入力、保存を順番に操作できる
- Modalキャンセル時にstop APIが呼ばれる
- 保存後にページ再読込しても登録済みボタンが残る
- 登録済みボタンを手動実行・モーションへバインドできる
- 赤外線の実状態をON/OFFとして誤表示しない
