# ESP32赤外線コントローラー HTTP API契約

| 項目 | 内容 |
|---|---|
| 対象 | ESP32ファームウェア担当者 |
| 呼び出し元 | Goバックエンド |
| APIバージョン | v1 |
| 最終更新日 | 2026-08-21 |
| ポート | TCP 80（既定） |

## 1. 役割分担

ESP32は赤外線信号の受信・送信と、送受信の排他制御を担当する。登録した機能名やデバイスとの紐付け、永続化、モーションとのバインディングはGoバックエンドが担当する。

```text
ESP32
├─ 赤外線を1件受信して構造化データを返す
├─ Goから渡された構造化信号を送信する
├─ 送信／学習を排他制御する
└─ Wi-Fi・内部状態を返す

Goバックエンド
├─ Deviceと機能名を保存する
├─ 受信信号をAction JSONとしてPostgreSQLへ保存する
├─ フロントエンドへ学習APIを提供する
└─ 手動操作またはジェスチャー時にESP32へ信号を渡す
```

既存のコンパイル済み `POST /api/send` や `/api/actions` は残してよいが、Goバックエンドの任意信号機能は本書のAPIを使用する。

v1ではGoバックエンド1インスタンスにつきESP32コントローラー1台を設定する。`controllerId` は将来の複数台対応と、保存済みActionの誤送信防止のために保持する。

## 2. 共通仕様

- HTTP/1.1
- JSONはUTF-8
- リクエスト／レスポンスのキーはcamelCase
- 成功レスポンスには `ok: true`
- 最大レスポンスサイズは1 MB未満
- 時刻を返す場合はRFC 3339 UTC
- 未定義JSONフィールドは無視してよい

### 2.1 認証

Goバックエンドはすべてのリクエストに次を付与する。

```http
X-API-Key: <IR_CONTROLLER_API_KEY>
```

ESP32は既存仕様との互換のため、次も受け付けてよい。

```http
Authorization: Bearer <IR_CONTROLLER_API_KEY>
```

未指定または不正な場合:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
```

```json
{
  "ok": false,
  "error": "unauthorized",
  "message": "API key is missing or invalid"
}
```

APIキーをログへ出力しない。

### 2.2 エラー形式

```json
{
  "ok": false,
  "error": "receive_in_progress",
  "message": "Sending is disabled while learning"
}
```

| Status | 用途 |
|---:|---|
| `400` | JSON、信号、repeat、timeoutが不正 |
| `401` | APIキー不正 |
| `404` | APIが存在しない |
| `408` | 学習タイムアウト |
| `409` | learning / sendingとの競合 |
| `500` | ESP32内部エラー |

## 3. 信号オブジェクト

受信と送信で同一形式を使用する。

```json
{
  "protocol": "NEC",
  "bits": 32,
  "code": "0x00FF18E7",
  "address": "0x00FF",
  "command": "0x18",
  "raw": [9000, 4500, 560, 560],
  "carrierHz": 38000
}
```

| フィールド | 必須 | 仕様 |
|---|---|---|
| `protocol` | 必須 | `NEC`, `SONY`, `RC5`, `UNKNOWN` など。英数字、`_+-`、最大32文字 |
| `bits` | code使用時 | 1〜1024 |
| `code` | 条件付き | `0x` 付き16進文字列。JSON数値にしない |
| `address` | 任意 | `0x` 付き16進文字列 |
| `command` | 任意 | `0x` 付き16進文字列 |
| `raw` | 条件付き | markから始まるmark/space交互のマイクロ秒配列。最大4096要素 |
| `carrierHz` | 必須 | 30000〜60000。現在の38kHz受信機では通常 `38000` |

`code` または `raw` の少なくとも一方が必須。

Goバックエンドは信号内容を解釈・ビット反転せず、受信時のオブジェクトをそのまま保存して送信時に返す。`code` のビット順はファームウェアで使用するIRライブラリの受信値と送信値がround-tripできる形式に統一する。

認識済みプロトコルでも可能ならRawを返す。Goバックエンドは両方を保存する。送信時は認識済みプロトコルを優先し、未対応または `UNKNOWN` ではRaw送信を使用する。

一般的な復調型38kHz受信モジュールは搬送波周波数を実測できない。その場合の `carrierHz` は設定値 `38000` を返す。実測値であるかのように扱わない。

## 4. 状態と排他制御

ランタイム状態:

| 状態 | 説明 |
|---|---|
| `idle` | 待機中 |
| `learning` | 赤外線受信待ち。送信を拒否 |
| `sending` | 送信中。受信結果を破棄 |
| `error` | 内部エラー |

学習APIのレスポンスでは、受信結果保持中を `captured` として返してよい。

必須ルール:

- `learning` 中の `/api/send/signal` と `/api/test/ir` は `409`
- `sending` 中の `/api/learn/start` は `409`
- 送信中は赤外線受信を停止または破棄する
- 送信終了後も短いガード時間を設け、自分の信号を受信しない
- `NEC Repeat` は新しいcaptureとして返さない
- 学習はone-shot。最初の通常信号を受信したら追加受信を停止する
- `/api/learn/stop` は冪等にし、すでに受信停止済みでも `200` を返す
- タイムアウト後は自動的に `idle` へ戻る

## 5. ヘルスチェック

```http
GET /api/health
X-API-Key: ...
```

レスポンス `200 OK`:

```json
{
  "ok": true,
  "state": "idle",
  "wifiConnected": true,
  "rssi": -52,
  "ip": "192.168.1.50",
  "firmwareVersion": "1.2.0"
}
```

Wi-Fi接続中でAPI処理可能なら `ok=true`。内部エラー時は `ok=false`, `state="error"` とメッセージを返す。

## 6. 動的信号送信

```http
POST /api/send/signal
Content-Type: application/json
X-API-Key: ...
```

```json
{
  "signal": {
    "protocol": "NEC",
    "bits": 32,
    "code": "0x00FF18E7",
    "address": "0x00FF",
    "command": "0x18",
    "raw": [9000, 4500, 560, 560],
    "carrierHz": 38000
  },
  "repeat": 1
}
```

- `repeat`: 必須、1〜5
- 指定回数を1リクエスト内で送信する
- HTTPタイムアウト後にGoは自動再送しないため、処理完了後に応答する

成功レスポンス:

```json
{
  "ok": true,
  "state": "idle",
  "sent": true
}
```

学習中:

```http
HTTP/1.1 409 Conflict
```

```json
{
  "ok": false,
  "error": "receive_in_progress",
  "message": "Sending is disabled while learning"
}
```

## 7. 学習開始

```http
POST /api/learn/start
Content-Type: application/json
X-API-Key: ...
```

```json
{
  "mode": "single",
  "timeoutSeconds": 30
}
```

| フィールド | 仕様 |
|---|---|
| `mode` | 現在は `single` のみ |
| `timeoutSeconds` | 5〜120 |

開始時に以前のcaptureを破棄する。

レスポンス:

```json
{
  "ok": true,
  "state": "learning"
}
```

すでにlearningまたはsendingの場合は `409 Conflict`。

## 8. 学習状態取得

```http
GET /api/learn/status
X-API-Key: ...
```

受信待ち:

```json
{
  "ok": true,
  "state": "learning",
  "capture": null,
  "expiresAt": "2026-08-21T03:00:30Z"
}
```

受信完了:

```json
{
  "ok": true,
  "state": "captured",
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

`captureId` は受信ごとに異なる安定したID。連番またはUUIDでよい。新しい `/api/learn/start` まで同じcaptureに同じIDを返す。

`NEC Repeat` を内部で検出した場合は破棄して `learning` を維持する。防御のため `isRepeat=true` を返してもGoバックエンド側で無視するが、通常は返さない。

タイムアウト:

```json
{
  "ok": false,
  "state": "timeout",
  "error": "learn_timeout",
  "message": "No infrared signal was received before timeout"
}
```

タイムアウト時は `408` または `200` のどちらでもGo側で処理できる。推奨は `408 Request Timeout`。

## 9. 学習停止

```http
POST /api/learn/stop
Content-Type: application/json
X-API-Key: ...
```

```json
{}
```

レスポンス:

```json
{
  "ok": true,
  "state": "idle"
}
```

受信完了後にGoバックエンドが必ず呼び出す。すでにone-shot受信でidleになっている場合も成功させる。

## 10. 赤外線LEDテスト

```http
POST /api/test/ir
Content-Type: application/json
X-API-Key: ...
```

```json
{}
```

スマートフォンのカメラで発光を確認できる短い38kHzテスト信号をGPIO13から送信する。

レスポンス:

```json
{
  "ok": true,
  "state": "idle"
}
```

learning中は `409 Conflict`。

## 11. Goバックエンド側設定

マイコンの接続先は次の環境変数で設定される。

```dotenv
IR_CONTROLLER_ID=main-ir
IR_CONTROLLER_URL=http://192.168.1.50
IR_CONTROLLER_API_KEY=<変更済みAPIキー>
IR_REQUEST_TIMEOUT_MS=3000
IR_LEARNING_TIMEOUT_SECONDS=30
```

LAN内でIPアドレスが変わらないよう、DHCP予約または固定IPを推奨する。Docker環境ではmDNS名が解決できない可能性があるため、疎通確認時はIPアドレスを優先する。

## 12. 結合試験チェックリスト

- 不正APIキーで全APIが401になる
- healthで `idle`, Wi-Fi情報、ファームウェア版を取得できる
- learn/start後に通常のNEC信号を1件取得できる
- 長押しのNEC Repeatが別captureにならない
- capture後に別ボタンを押してもcaptureが上書きされない
- stopを複数回呼んでも200になる
- learning中のsend/testが409になる
- send/signalでcode送信とRaw送信の両方が動作する
- repeat=1とrepeat=5が指定回数送信される
- 送信直後の自己受信が学習結果にならない
- タイムアウト後にidleへ復帰する
