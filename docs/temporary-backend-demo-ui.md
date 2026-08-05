# 仮バックエンドデモUI

> `TEMP_BACKEND_DEMO` — この画面は正式なフロントエンドではない。バックエンドAPIの結合確認とデモを目的とした仮実装である。

## 1. 目的と扱い

- Goバックエンドが公開するAPIをブラウザから確認する
- モーションと家電アクションの紐付けを試す
- Tuyaアクションを手動実行し、操作ログを確認する
- 正式フロントの画面設計、コンポーネント設計、状態管理方式を決めるものではない
- 正式フロントが利用可能になった時点で、この画面を削除または置き換える

画面URLは次のとおり。

```text
http://localhost:5173/backend-demo
```

API接続先は `VITE_API_BASE_URL` で変更する。未設定時は `http://localhost:8080` を使用する。

## 2. 実装ファイル

| ファイル | 役割 | 削除時の扱い |
| --- | --- | --- |
| `front/app/routes/backend-demo.tsx` | 画面、API読込、紐付け保存、手動実行、ログ表示 | ファイルを削除 |
| `front/app/routes/backend-demo.css` | `/backend-demo` 専用スタイル | ファイルを削除 |
| `front/app/services/backendApiClient.ts` | 仮画面専用のHTTPクライアント | 正式フロントから未使用なら削除 |
| `front/app/types/backendApi.ts` | 仮画面専用のAPI型定義 | 正式フロントから未使用なら削除 |
| `front/app/routes.ts` | `/backend-demo` のルート登録1行 | 対象ルートとコメントを削除 |
| `docs/backend-api-specification.md` | 仮画面の案内と本書へのリンク | 「仮フロントでの試用」を削除 |

追加のnpmパッケージや共通コンポーネントへの変更はない。仮実装の対象は次のコマンドで検索できる。

```bash
rg -n "TEMP_BACKEND_DEMO|backend-demo" front/app docs
```

## 3. 画面の機能

### 接続状態と登録状況

- API接続先を表示する
- カメラ、モーション、家電、アクション、紐付け、直近ログを並列取得する
- モーション数、家電数、紐付け数、ログ数を表示する
- 再読み込みボタンで最新状態を取得する

### モーションの紐付け

- 登録済みモーションごとに実行アクションを選択する
- 将来用メタデータとして任意の `cameraId` を保存できる
- 現在のバックエンドはモーションをキーにアクションを決定し、`cameraId` でアクションを切り替えない
- アクション未選択時は保存ボタンを無効にする

### Tuya手動テスト

- 登録済みアクションを一覧表示する
- ボタン押下で対象アクションを即時実行する
- 実行後にデータと操作ログを再取得する
- `TUYA_DRY_RUN=false` のバックエンドへ接続している場合、確認ダイアログなしで実機が動作する

### 操作ログ

- 成功、失敗、クールダウンを日本語で表示する
- モーション、実行アクション、カメラ、検出日時を表示する
- 手動実行は `MANUAL_TRIGGER` として記録される

## 4. 利用するバックエンドAPI

| Method | Path | 用途 |
| --- | --- | --- |
| `GET` | `/api/cameras` | カメラ一覧 |
| `GET` | `/api/motions` | モーション一覧 |
| `GET` | `/api/appliances` | 家電一覧 |
| `GET` | `/api/actions` | 実行アクション一覧 |
| `GET` | `/api/bindings` | モーション紐付け一覧 |
| `GET` | `/api/logs?limit=20` | 直近の操作ログ |
| `POST` | `/api/bindings` | モーション紐付けの保存 |
| `POST` | `/api/actions/:id/execute` | Tuyaアクションの手動実行 |

リクエストとレスポンスの正式な仕様は [バックエンドAPI仕様書](./backend-api-specification.md) を参照する。

## 5. 起動方法

### Dry-runで確認する

バックエンドを起動する。

```bash
cd backend
TUYA_DRY_RUN=true PORT=8080 ALLOWED_ORIGINS=http://localhost:5173 go run ./cmd/server
```

別ターミナルでフロントを起動する。

```bash
cd front
VITE_API_BASE_URL=http://localhost:8080 npm run dev
```

### Tuya実機で確認する

`backend/.env` にTuya認証情報とDevice IDを設定した上で起動する。

```bash
cd backend
set -a
source .env
set +a
TUYA_DRY_RUN=false PORT=8080 ALLOWED_ORIGINS=http://localhost:5173 go run ./cmd/server
```

フロントの起動方法はDry-run時と同じ。

実機モードでは手動テストボタンを押すと直ちに家電が動作する。共有環境での誤操作に注意すること。認証情報、Access Secret、Device IDをソースコードやコミットへ含めないこと。

## 6. 仮実装の制約

- API認証・認可を実装していない
- 手動実行前の確認ダイアログがない
- API接続先がDry-runか実機かをフロントだけでは判別できない
- データ更新は再取得方式で、WebSocketなどのリアルタイム更新はない
- ログ表示は直近20件に固定している
- 正式なデザインシステムや共通コンポーネントを使用していない
- エラー表示とアクセシビリティはデモに必要な最小限のみ対応している
- `DATABASE_URL` 未設定時はインメモリ保存のため、バックエンド再起動で紐付けとログが消える

## 7. 正式フロントへの引き継ぎ

正式フロントでは [バックエンドAPI仕様書](./backend-api-specification.md) を正とする。本実装から再利用する場合も、画面コンポーネントをそのまま正式化するのではなく、必要なAPI呼び出しと型定義を選んで移植する。

特に次を再検討すること。

- APIクライアントの配置、認証、共通エラーハンドリング
- 実機操作前の確認と権限制御
- Dry-run／実機モードの明示
- モーション紐付けの正式な画面導線
- ログのページネーションと自動更新
- 共通デザインシステムへの統合

## 8. 完全に削除する手順

仮フロントだけの独立コミットになっている場合は、そのコミットをrevertするのが最も簡単である。手作業で削除する場合は次の順序で行う。

1. `front/app/routes.ts` から `backend-demo` のルートと `TEMP_BACKEND_DEMO` コメントを削除する
2. `front/app/routes/backend-demo.tsx` を削除する
3. `front/app/routes/backend-demo.css` を削除する
4. 正式フロントから未使用なら `front/app/services/backendApiClient.ts` を削除する
5. 正式フロントから未使用なら `front/app/types/backendApi.ts` を削除する
6. `docs/backend-api-specification.md` の「仮フロントでの試用」を削除する
7. 本書 `docs/temporary-backend-demo-ui.md` を削除する
8. `rg -n "TEMP_BACKEND_DEMO|backend-demo" front/app docs` の結果が空であることを確認する
9. `cd front && npm run typecheck && npm run build` を実行する

正式フロントがAPIクライアントや型定義を再利用した場合は、手順4・5のファイルを削除せず、`TEMP_BACKEND_DEMO` コメントと配置を正式実装向けに整理する。
