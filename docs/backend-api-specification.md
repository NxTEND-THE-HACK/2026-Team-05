# バックエンドAPI仕様書

| 項目 | 内容 |
|---|---|
| 対象 | フロントエンド・Python認識サービス開発者 |
| APIバージョン | v0.1.0 |
| 最終更新日 | 2026-08-05 |
| 実装ブランチ | `codex/feature/backend-tuya` |
| OpenAPI | `backend/openapi.yaml` |

## 1. 概要

このバックエンドは、以下の2種類のAPIを提供する。

- `/api/*`: フロントエンドが家電、アクション、モーションとの紐付け、操作ログを管理するREST API
- `/internal/*`: Python認識サービスからモーション認識結果を受け取る内部API

現在の紐付けモデルは次のとおり。

```text
Motion（認識された動作）
  ↓ 1モーションにつき1アクション
Action（例: プラグAをオン）
  ↓
Appliance（例: スマートプラグA）
```

`camera_id` は認識元の確認と操作ログに使用する。紐付けには将来利用するための任意メタデータとして `cameraId` を保存できるが、現時点では家電アクションの選択条件には使用しない。同じモーションが異なる登録済みカメラから届いた場合も、同じアクションが実行される。

## 2. フロントエンド側で必要な型変更

現在の `front/app/types/api.ts` は旧仕様のため、API接続時に次の変更が必要になる。

```ts
export type ActionProviderType = "TUYA";

export interface MotionBinding {
  id: string;
  cameraId?: string;
  motionId: string;
  actionId: string;
  isEnabled: boolean;
  createdAt: string;
}

export interface CreateBindingRequest {
  cameraId?: string;
  motionId: string;
  actionId: string;
}
```

変更点:

- `ActionProviderType` は現在 `TUYA` のみ対応
- `MotionBinding.cameraId` は将来利用のためoptionalで保持
- `CreateBindingRequest.cameraId` もoptional
- 現在のアクション検索では `cameraId` を使用しない
- モーションとアクションを直接紐付ける

## 3. 共通仕様

### 3.1 ベースURL

ローカル開発時:

```text
http://localhost:8080
```

ポートはバックエンドの `PORT` 環境変数で変更できる。

### 3.2 データ形式

- リクエスト・レスポンスはJSON
- POSTリクエストは `Content-Type: application/json` が必須
- POSTリクエストの最大サイズは1 MB
- 日時はRFC 3339形式
- IDはすべて文字列
- POSTリクエストに未定義フィールドがある場合は `400 Bad Request`

### 3.3 CORS

デフォルトでは次のOriginを許可する。

```text
http://localhost:5173
```

許可Originはバックエンドの `ALLOWED_ORIGINS` 環境変数でカンマ区切り指定できる。

### 3.4 認証

現在は認証なし。同一LAN内でのデモ運用を前提とする。

### 3.5 エラーレスポンス

```json
{
  "error": "エラー内容"
}
```

主なHTTPステータス:

| Status | 意味 |
|---|---|
| `400` | JSON形式、必須項目、値が不正 |
| `404` | 指定された家電・アクションなどが存在しない |
| `409` | 一意制約に違反した |
| `413` | リクエストボディが1 MBを超えた |
| `415` | `Content-Type` が `application/json` ではない |
| `500` | バックエンド内部エラー |
| `503` | DBなどの保存先が利用できない |

## 4. API一覧

| Method | Path | 用途 | 主な利用者 |
|---|---|---|---|
| `GET` | `/healthz` | ヘルスチェック | 全コンポーネント |
| `POST` | `/internal/detections` | モーション認識結果の受信 | Python |
| `GET` | `/api/cameras` | カメラ一覧 | フロント |
| `GET` | `/api/motions` | モーション一覧 | フロント |
| `GET` | `/api/appliances` | 家電一覧 | フロント |
| `POST` | `/api/appliances` | 家電作成 | フロント |
| `GET` | `/api/actions` | 家電アクション一覧 | フロント |
| `POST` | `/api/actions` | 家電アクション作成 | フロント |
| `POST` | `/api/actions/:id/execute` | 家電アクション手動実行 | フロント |
| `GET` | `/api/bindings` | モーション紐付け一覧 | フロント |
| `POST` | `/api/bindings` | モーション紐付け作成・更新 | フロント |
| `DELETE` | `/api/bindings/:id` | モーション紐付け削除 | フロント |
| `GET` | `/api/logs` | 操作ログ一覧 | フロント |

## 5. フロントエンド向けAPI

### 5.1 カメラ一覧取得

```http
GET /api/cameras
```

レスポンス `200 OK`:

```json
{
  "cameras": [
    {
      "id": "demo-camera-1",
      "name": "カメラ1",
      "streamUrl": "",
      "location": "デモエリア1",
      "isEnabled": true,
      "createdAt": "2026-08-05T03:00:00Z"
    }
  ]
}
```

現在、カメラの作成・編集・削除APIはない。

### 5.2 モーション一覧取得

```http
GET /api/motions
```

レスポンス `200 OK`:

```json
{
  "motions": [
    {
      "id": "motion-pose-right-hand-up",
      "code": "POSE_RIGHT_HAND_UP",
      "name": "右手上げ",
      "description": "右手首を右肩より上で0.6秒保持"
    },
    {
      "id": "motion-swipe-right",
      "code": "MOTION_SWIPE_RIGHT",
      "name": "右スワイプ",
      "description": "右手を右方向へスワイプ"
    },
    {
      "id": "motion-finger-snap",
      "code": "MOTION_FINGER_SNAP",
      "name": "指パッチン",
      "description": "右手を曲げた準備姿勢から人差し指を伸ばす"
    },
    {
      "id": "motion-thumbs-up-move-up",
      "code": "MOTION_THUMBS_UP_MOVE_UP",
      "name": "Goodから上",
      "description": "右手を親指上の状態にして上へ動かす"
    },
    {
      "id": "motion-thumbs-down-move-down",
      "code": "MOTION_THUMBS_DOWN_MOVE_DOWN",
      "name": "Badから下",
      "description": "右手を親指下の状態にして下へ動かす"
    },
    {
      "id": "motion-clap",
      "code": "MOTION_CLAP",
      "name": "拍手",
      "description": "左右の手を離した状態から近づけて叩く"
    },
    {
      "id": "motion-open-to-fist-down",
      "code": "MOTION_OPEN_TO_FIST_DOWN",
      "name": "パーからグーで下げる",
      "description": "右手をパーからグーにしながら下へ動かす"
    },
    {
      "id": "motion-hand-rotate-right",
      "code": "MOTION_HAND_ROTATE_RIGHT",
      "name": "右回し",
      "description": "右手の手のひらを基準から時計回りに30度以上回す"
    },
    {
      "id": "motion-hand-rotate-left",
      "code": "MOTION_HAND_ROTATE_LEFT",
      "name": "左回し",
      "description": "左手の手のひらを基準から反時計回りに30度以上回す"
    }
  ]
}
```

モーションはPython認識サービスの実装と対応する固定データ。現在、作成・編集・削除APIはない。

### 5.3 家電一覧取得

```http
GET /api/appliances
```

レスポンス `200 OK`:

```json
{
  "appliances": [
    {
      "id": "appliance-plug-a",
      "name": "スマートプラグA",
      "category": "スマートプラグ",
      "createdAt": "2026-08-05T03:00:00Z"
    }
  ]
}
```

### 5.4 家電作成

```http
POST /api/appliances
Content-Type: application/json
```

リクエスト:

```json
{
  "name": "リビング照明",
  "category": "照明"
}
```

レスポンス `201 Created`:

```json
{
  "id": "appliance-xxxxxxxx-xxxx-4xxx-xxxx-xxxxxxxxxxxx",
  "name": "リビング照明",
  "category": "照明",
  "createdAt": "2026-08-05T03:00:00Z"
}
```

`name` と `category` は必須。

### 5.5 家電アクション一覧取得

すべて取得:

```http
GET /api/actions
```

家電IDで絞り込み:

```http
GET /api/actions?applianceId=appliance-plug-a
```

レスポンス `200 OK`:

```json
{
  "actions": [
    {
      "id": "action-plug-a-on",
      "applianceId": "appliance-plug-a",
      "name": "プラグA オン",
      "providerType": "TUYA",
      "params": {
        "deviceIdEnv": "PLUG_A_ID",
        "switchCode": "switch",
        "value": true
      }
    }
  ]
}
```

### 5.6 家電アクション作成

```http
POST /api/actions
Content-Type: application/json
```

環境変数に登録されたDevice IDを使用する例:

```json
{
  "applianceId": "appliance-plug-a",
  "name": "プラグA オン",
  "providerType": "TUYA",
  "params": {
    "deviceIdEnv": "PLUG_A_ID",
    "switchCode": "switch",
    "value": true
  }
}
```

Device IDを直接指定する例:

```json
{
  "applianceId": "appliance-plug-a",
  "name": "プラグA オフ",
  "providerType": "TUYA",
  "params": {
    "deviceId": "tuya-device-id",
    "switchCode": "switch",
    "value": false
  }
}
```

Tuyaパラメータ:

| Field | Type | 必須 | 内容 |
|---|---|---|---|
| `deviceIdEnv` | string | 条件付き | `PLUG_A_ID`, `PLUG_B_ID`, `PLUG_C_ID` のいずれか |
| `deviceId` | string | 条件付き | Tuya Device IDを直接指定 |
| `switchCode` | string | 任意 | Tuyaの電源DPコード。省略時は `switch` |
| `value` | boolean | 必須 | `true`: オン、`false`: オフ |

`deviceIdEnv` と `deviceId` はどちらか一方だけ指定する。

レスポンス `201 Created` は作成された `Action` オブジェクトを直接返す。

### 5.7 家電アクション手動実行

```http
POST /api/actions/{actionId}/execute
```

リクエストボディは不要。

成功レスポンス `200 OK`:

```json
{
  "success": true
}
```

Tuya操作失敗時もHTTPレスポンスは `200 OK` で、次の形式になる。

```json
{
  "success": false,
  "message": "Tuya rejected command: code=xxxx message=..."
}
```

実行結果は操作ログへ保存される。

### 5.8 モーション紐付け一覧取得

```http
GET /api/bindings
```

レスポンス `200 OK`:

```json
{
  "bindings": [
    {
      "id": "binding-xxxxxxxx-xxxx-4xxx-xxxx-xxxxxxxxxxxx",
      "cameraId": "demo-camera-1",
      "motionId": "motion-pose-right-hand-up",
      "actionId": "action-plug-a-on",
      "isEnabled": true,
      "createdAt": "2026-08-05T03:00:00Z"
    }
  ]
}
```

### 5.9 モーション紐付け作成・更新

```http
POST /api/bindings
Content-Type: application/json
```

リクエスト:

```json
{
  "cameraId": "demo-camera-1",
  "motionId": "motion-pose-right-hand-up",
  "actionId": "action-plug-a-on"
}
```

レスポンス `201 Created`:

```json
{
  "id": "binding-xxxxxxxx-xxxx-4xxx-xxxx-xxxxxxxxxxxx",
  "cameraId": "demo-camera-1",
  "motionId": "motion-pose-right-hand-up",
  "actionId": "action-plug-a-on",
  "isEnabled": true,
  "createdAt": "2026-08-05T03:00:00Z"
}
```

動作:

- 1つのモーションには1つのアクションを紐付ける
- `cameraId` は任意。指定時は登録済みカメラか検証して保存する
- 保存した `cameraId` は将来利用予約で、現在のアクション検索には使用しない
- そのモーションの紐付けが未登録の場合は新規作成
- すでに紐付けがある場合は `actionId` を更新
- 更新の場合もHTTPステータスは `201 Created`
- 更新時はクールダウン状態をリセット

### 5.10 モーション紐付け削除

```http
DELETE /api/bindings/{id}
```

指定したバインディングIDの紐付けを削除する。

レスポンス `204 No Content`:

- 対象が存在する場合はボディなしで返す
- 対象が存在しない場合は `404 Not Found` を返す

### 5.11 操作ログ一覧取得

```http
GET /api/logs
```

件数指定:

```http
GET /api/logs?limit=100
```

- デフォルト: 100件
- 最小: 1件
- 最大: 500件
- 新しいログから順に返す

レスポンス `200 OK`:

```json
{
  "logs": [
    {
      "id": "log-xxxxxxxx-xxxx-4xxx-xxxx-xxxxxxxxxxxx",
      "eventId": "f6e30b95-7f98-4f68-aef2-a1d4b0f27af5",
      "cameraId": "demo-camera-1",
      "cameraName": "カメラ1",
      "motionCode": "POSE_RIGHT_HAND_UP",
      "motionName": "右手上げ",
      "actionId": "action-plug-a-on",
      "actionName": "プラグA オン",
      "status": "SUCCESS",
      "detectedAt": "2026-08-05T03:00:00Z"
    }
  ]
}
```

ログステータス:

| Status | 意味 |
|---|---|
| `SUCCESS` | Tuya操作成功 |
| `FAILED` | カメラ、モーション、紐付け、Tuya操作などで失敗 |
| `COOLING_DOWN` | 同じモーションのクールダウン中 |

紐付け解決前に失敗したログでは `actionId` と `actionName` が存在しない。

## 6. Python認識サービス向けAPI

フロントエンドから通常使用する必要はない。

### 6.1 モーション認識結果送信

```http
POST /internal/detections
Content-Type: application/json
```

リクエスト:

```json
{
  "event_id": "f6e30b95-7f98-4f68-aef2-a1d4b0f27af5",
  "camera_id": "demo-camera-1",
  "motion_code": "POSE_RIGHT_HAND_UP",
  "confidence": 0.93,
  "detected_at": "2026-08-05T12:00:00+09:00"
}
```

バリデーション:

| Field | 条件 |
|---|---|
| `event_id` | 必須、128文字以内 |
| `camera_id` | 必須、登録済みかつ有効なカメラ |
| `motion_code` | 必須、登録済みモーションコード |
| `confidence` | 0〜1。現在は閾値判定には未使用 |
| `detected_at` | 必須、RFC 3339形式 |

レスポンス例:

```json
{
  "status": "executed",
  "log": {
    "id": "log-xxxxxxxx-xxxx-4xxx-xxxx-xxxxxxxxxxxx",
    "eventId": "f6e30b95-7f98-4f68-aef2-a1d4b0f27af5",
    "cameraId": "demo-camera-1",
    "motionCode": "POSE_RIGHT_HAND_UP",
    "actionId": "action-plug-a-on",
    "status": "SUCCESS",
    "detectedAt": "2026-08-05T12:00:00+09:00"
  }
}
```

認識処理結果:

| `status` | 意味 | Tuya呼び出し |
|---|---|---|
| `executed` | アクション実行成功 | あり |
| `failed` | Tuyaアクション実行失敗 | あり |
| `duplicate` | 同じ `event_id` を処理済み | なし |
| `cooling_down` | モーションのクールダウン中 | なし |
| `rejected` | カメラ、モーション、紐付けが存在しない | なし |

これらの業務上の結果はすべて `200 OK` で返す。不正なJSONやバリデーション違反だけが `400` になる。

### 6.2 重複排除

一度処理した `event_id` は再実行しない。PythonがHTTP再送した場合も、同じ家電操作が二重に行われることを防ぐ。

```json
{
  "status": "duplicate"
}
```

### 6.3 クールダウン

同じモーションに紐付いたアクションの連続実行を防ぐ。デフォルトは5秒。

```dotenv
ACTION_COOLDOWN_SECONDS=5
```

クールダウンはモーション紐付け単位で管理される。

## 7. ヘルスチェック

```http
GET /healthz
```

正常時 `200 OK`:

```json
{
  "status": "ok"
}
```

保存先へ接続できない場合は `503 Service Unavailable`。

## 8. フロント画面からの推奨利用順

設定画面:

1. `GET /api/motions` でモーション候補を取得
2. `GET /api/appliances` で家電候補を取得
3. `GET /api/actions?applianceId=...` で家電のオン・オフ操作を取得
4. `POST /api/bindings` でモーションとアクションを紐付け
5. `POST /api/actions/:id/execute` で実機を手動テスト

ダッシュボード・ログ画面:

1. `GET /api/bindings` で現在の設定を取得
2. `GET /api/logs?limit=100` で操作履歴を取得
3. 必要に応じてカメラ、モーション、アクション一覧とIDを突合

## 9. 現在未実装のAPI

- カメラの作成・編集・削除
- モーションの作成・編集・削除
- 家電の編集・削除
- アクションの編集・削除
- ログのページネーション、期間・ステータス絞り込み
- WebSocketなどによるリアルタイム通知
- API認証・認可

フロント側では、これらの操作ボタンを現時点で表示しないか、未実装として扱う。

## 10. 実装上の注意

- `DATABASE_URL` が未設定の場合、データはインメモリ保存となり、バックエンド再起動時に作成データ・紐付け・ログが消える
- PostgreSQL利用時はデータが永続化される
- `TUYA_DRY_RUN=true` の場合、APIは成功するが実機操作は行わない
- 実機操作ではTuya Device IDと電源DPコードが正しい必要がある
- 現在の初期データにはプラグA〜Cのオン・オフアクションがあるが、モーションとの初期紐付けはない
