# Backend

ジェスチャー認識イベントを受け取り、モーションに紐付けられた家電アクションに従ってTuyaスマートプラグをオン・オフするGo APIです。フロントエンド向けの管理・ログAPIも同じサーバーから提供します。

## 処理フロー

```text
Python recognition worker
  -> POST /internal/detections
  -> event_id重複排除
  -> motion_codeで明示的に設定されたアクションを解決
  -> 紐付け単位のクールダウン
  -> Tuya Cloud API
  -> action_logsへ結果を記録
```

同じ `event_id` が再送された場合は `status: duplicate` を返し、家電操作を再実行しません。映像データは受け取らず、保存もしません。

## ローカル起動

Go 1.25以降を使用します。

```bash
cd backend
cp .env.example .env
set -a
source .env
set +a
go run ./cmd/server
```

`.env.example` は `TUYA_DRY_RUN=true` なので、認証情報や実機なしでAPI全体を確認できます。`.env` はアプリが自動では読み込まないため、上記のようにシェルへ読み込むか、コンテナの `--env-file` を使用してください。

`DATABASE_URL` が空の場合はインメモリ保存になります。PostgreSQL URLを設定すると、起動時に `internal/store/migrations` のスキーマと初期データを適用します。

## Tuya実機設定

```dotenv
TUYA_ACCESS_ID=TuyaプロジェクトのAccess ID
TUYA_SECRET_KEY=TuyaプロジェクトのAccess Secret
TUYA_REGION=us
TUYA_DRY_RUN=false

PLUG_A_ID=プラグAのDevice ID
PLUG_B_ID=プラグBのDevice ID
PLUG_C_ID=プラグCのDevice ID
```

`TUYA_REGION` は `jp`, `us`, `eu`, `cn`, `in` に対応します。Tuya Cloudプロジェクトでは対象デバイスをリンクし、デバイス制御APIを利用できるようにしてください。

初期アクションのTuyaパラメータは次の形式です。

```json
{
  "deviceIdEnv": "PLUG_A_ID",
  "switchCode": "switch",
  "value": true
}
```

- `deviceIdEnv`: `PLUG_A_ID` / `PLUG_B_ID` / `PLUG_C_ID` のいずれか
- `deviceId`: 環境変数の代わりにDevice IDを直接指定する場合に使用
- `switchCode`: Tuyaデバイスの電源DPコード。既定値は `switch`
- `value`: `true` でオン、`false` でオフ

製品によって電源DPコードが `switch_1` などの場合があります。その場合はアクション作成時の `switchCode` をTuya API Explorerに表示されるコードへ変更してください。

LINE Botは今回の認識経路では使用しないため、`LINE_SECRET` と `LINE_TOKEN` は不要です。

## カメラとアクションの扱い

`camera_id` はPythonが認識に使用したカメラ（部屋・入力元）の検証と操作ログに使用します。紐付けにも将来利用できる任意メタデータとして `cameraId` を保存できますが、現時点では家電アクションの検索条件には使用しません。

初期データにはカメラ、認識サービス側に実装済みのモーション、プラグA〜Cのオン・オフアクションだけを登録します。モーションとアクションの紐付けは初期登録しません。紐付けがない認識JSONを受け取った場合はTuyaを呼ばず、`FAILED` ログを残します。

紐付けはフロントまたは `POST /api/bindings` から明示的に設定します。同じモーションに紐付けられるアクションは1つで、再設定すると指定したアクションへ更新します。不要になった紐付けは `DELETE /api/bindings/:id` で削除できます。

## 疎通確認

```bash
curl http://localhost:8080/healthz

curl -X POST http://localhost:8080/api/bindings \
  -H 'Content-Type: application/json' \
  -d '{
    "cameraId":"demo-camera-1",
    "motionId":"motion-pose-right-hand-up",
    "actionId":"action-plug-a-on"
  }'

curl -X POST http://localhost:8080/internal/detections \
  -H 'Content-Type: application/json' \
  -d '{
    "event_id":"00000000-0000-4000-8000-000000000001",
    "camera_id":"demo-camera-1",
    "motion_code":"POSE_RIGHT_HAND_UP",
    "confidence":0.93,
    "detected_at":"2026-08-05T12:00:00+09:00"
  }'

curl http://localhost:8080/api/logs
```

認識ワーカーは次を指定します。

```dotenv
GO_API_URL=http://127.0.0.1:8080/internal/detections
```

## API

| Method | Path | 用途 |
|---|---|---|
| `GET` | `/healthz` | ヘルスチェック |
| `POST` | `/internal/detections` | Pythonから認識イベントを受信 |
| `GET` | `/api/cameras` | カメラ一覧 |
| `GET` | `/api/motions` | モーション一覧 |
| `GET` / `POST` | `/api/appliances` | 家電一覧・追加 |
| `GET` / `POST` | `/api/actions` | アクション一覧・追加 |
| `POST` | `/api/actions/:id/execute` | 手動実行 |
| `GET` / `POST` | `/api/bindings` | 紐付け一覧・作成または更新 |
| `DELETE` | `/api/bindings/:id` | 紐付け削除 |
| `GET` | `/api/logs?limit=100` | 操作ログ。最大500件 |

リストAPIのレスポンスはフロントの既存型に合わせて `{ "cameras": [...] }` のような包み形式です。作成APIは作成したオブジェクトを直接返します。バックエンドでは `providerType: "TUYA"` を追加しているため、フロント側の `ActionProviderType` にもマージ時に `"TUYA"` を加えてください。

## テスト

```bash
go test ./...
```

テストではTuya Cloudへ通信せず、イベント重複排除、クールダウン、JSON検証、未設定カメラから家電を推測しないこと、フロント向けレスポンス形式を確認します。
