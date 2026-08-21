# フロントエンド仕様書

| 項目 | 内容 |
|---|---|
| 対象 | フロントエンド開発者・バックエンド連携担当 |
| プロダクト名 | Remo-Trace |
| 実装ディレクトリ | `front/` |
| 最終更新日 | 2026-08-21 |
| 実装ブランチ | `feature/implement-ui-screens` |
| 関連仕様 | `docs/backend-api-specification.md`, `docs/frontend-ir-api-specification.md`, `docs/mvp-specification.md` |

---

## 1. 概要

Remo-Trace フロントエンドは、ジェスチャー操作型スマートホームの **管理 UI** を提供する。

主な責務:

- モーション・家電（Appliance）・アクション・バインディング・実行ログの閲覧
- モーションとアクションのバインディング作成
- 家電の簡易登録
- デバイス詳細からの **手動アクション実行**（ON/OFF 等。モーション経由ではない）
- バックエンド死活の可視化（`GET /healthz`）

認識パイプライン（カメラ / Python）自体は扱わない。操作対象はバックエンド REST API（`/api/*`, `/healthz`）のみ。

---

## 2. 技術スタック

| カテゴリ | 技術 | 備考 |
|---|---|---|
| フレームワーク | React Router v8（`@react-router/*`） | ファイルベースルート、SSR ビルド可 |
| UI | Ant Design v6（`antd@^6`） | CSS Variables 既定 |
| アイコン | `@ant-design/icons@^6` | antd v6 必須 |
| データ取得 | TanStack Query v5 | キャッシュ・再取得・ミューテーション |
| 言語 | TypeScript 5.9（strict） | |
| ビルド | Vite 8 | `@react-router/dev` |
| 補助 CSS | Tailwind CSS v4 | 補助用途。主要 UI は antd |
| ランタイム | React 19 | |

### 2.1 開発・ビルドコマンド

```bash
cd front
npm run dev        # 開発サーバ（既定 http://localhost:5173）
npm run typecheck  # typegen + tsc
npm run build      # 本番ビルド
npm run start      # ビルド成果物の serve
```

---

## 3. 環境変数

| 変数 | 必須 | 既定値 | 説明 |
|---|---|---|---|
| `VITE_API_BASE_URL` | 否 | `http://localhost:8080` | バックエンド API のベース URL（末尾 `/` はクライアント側で除去） |

- 定義場所の例: `front/.env`（**git 管理外**。`.env` / `.env.*` は ignore、`.env.example` のみ許可）
- 参照: `front/app/services/backendApiClient.ts` の `import.meta.env.VITE_API_BASE_URL`

---

## 4. デザイン・テーマ

Proxmox VE 系管理画面を参考にした **ヘッダー全幅 + 左サイドバー + コンテンツ** レイアウト。

### 4.1 テーマトークン（`root.tsx`）

| 項目 | 値 |
|---|---|
| algorithm | `theme.darkAlgorithm`（ダークモード固定） |
| `colorPrimary` | `#1677ff` |
| `borderRadius` | `0`（角丸なし） |

### 4.2 レイアウト構造

```text
+----------------------------------------------------------+
| Header（全幅）                                             |
|   左: Remo-Trace    右: ApiStatusBadge（/healthz）         |
+------------+---------------------------------------------+
| Sider      | Content（padding: 48px）                     |
| 折りたたみ可 | 各ページ本体                                |
|            |                                              |
| · Dashboard|                                              |
| · Devices  |                                              |
|   └ <name> |  → /devices/:deviceId                        |
+------------+---------------------------------------------+
```

実装上の注意:

- `AppLayout` は React Router の `layout()` 用に **default export** 必須
- コンテンツ背景は antd token（`colorBgLayout` 等）を使用し、ライト固定色は使わない
- 詳細系ページには `BackToDashboard`（`/` へ戻る）を配置

### 4.3 サイドバーメニュー

| 項目 | 遷移先 | データ源 |
|---|---|---|
| Dashboard | `/` | 固定 |
| Devices グループ配下の各家電名 | `/devices/:deviceId` | `GET /api/appliances` |

---

## 5. ルーティング

定義: `front/app/routes.ts`

| パス | ルートファイル | ページコンポーネント | 用途 |
|---|---|---|---|
| `/` | `routes/dashboard.tsx` | `DashboardPage` | サマリー + 直近ログ |
| `/motions` | `routes/motions.tsx` | `MotionsPage` | モーション一覧 |
| `/devices` | `routes/devices.tsx` | `DevicesPage` | 家電一覧・登録 |
| `/devices/:deviceId` | `routes/device-detail.tsx` | `DeviceDetailPage` | 家電詳細・手動制御 |
| `/bindings` | `routes/bindings.tsx` | `BindingsPage` | バインディング管理 |
| `/logs` | `routes/logs.tsx` | `LogsPage` | 実行ログ一覧 |

全ルートは `components/layout/AppLayout.tsx` 配下。

---

## 6. 画面仕様

### 6.1 Dashboard（`/`）

| 要素 | 仕様 |
|---|---|
| サマリーカード ×4 | Motions / Devices / Bindings / Recent Logs の件数（`Statistic`） |
| カードクリック | それぞれ `/motions`, `/devices`, `/bindings`, `/logs` へ遷移 |
| Recent Logs | `LogsTable`。`useLogs(100)` |
| 件数算出 | 各一覧 API の配列長（集計専用 API なし） |

レスポンシブ: サマリーは `Row` + `Col`（`xs=24 sm=12 md=6` 相当）。

### 6.2 Motions（`/motions`）

- `GET /api/motions` の一覧テーブル
- 列の目安: 名称、コード、説明 等
- `BackToDashboard`

### 6.3 Devices（`/devices`）

- `GET /api/appliances` 一覧
- 行クリックまたはリンクで `/devices/:id`
- 簡易登録フォーム（名称・カテゴリ・操作方式）→ `POST /api/appliances`（実装に準拠）
- `BackToDashboard`

### 6.4 Device Detail（`/devices/:deviceId`）

| セクション | 仕様 |
|---|---|
| 基本情報 | 一覧から `deviceId` で検索した Appliance（単体 GET 未使用） |
| 関連バインディング | 当該 appliance の action に紐づく bindings をテーブル表示 |
| **Manual Control** | `controlProvider` に応じてTuya Switchまたは赤外線ボタンを表示 |

#### Tuya Manual Control 詳細

- データ: `useActions(deviceId)` および appliance 絞り込み
- 並び: `params.value === true`（ON 系）を優先、その後 OFF、名称ソート
- 実行: `POST /api/actions/:id/execute`（`useExecuteAction`）
- UX:
  - 実行中は対象ボタンを loading
  - 成功/失敗は `message.success` / `message.error`
  - 成功時は logs クエリを invalidate
- ボタンラベル目安: `params.value === true` → ON 系、`false` → OFF 系、それ以外 → 実行

未存在 ID: 一覧に該当なしのとき空状態 / Result 表示。

#### ESP32赤外線 Manual Control

- `controlProvider === "ESP32_IR"` の場合だけ表示
- 登録済みActionをボタングリッドで表示し、既存execute APIで送信
- `＋ ボタンを登録` からone-shot学習Modalを開く
- 学習中は当該コントローラーの送信ボタンをdisabledにする
- 詳細なAPI、型、状態遷移は `docs/frontend-ir-api-specification.md` を正とする

### 6.5 Bindings（`/bindings`）

| 機能 | 仕様 |
|---|---|
| 一覧 | Device 名 / Motion / Action / Enabled 等（関連マスタを join 表示） |
| New Motion（バインディング作成） | `Modal` + Form。Motion 選択、Action 選択（appliance グループ可）→ `POST /api/bindings` |
| 削除（Del） | UI は表示。押下時は **警告のみ**（BE に DELETE 未実装）。文言例: 「バインディング削除はバックエンド未対応です」 |

`DeviceBindingPanel` / `NewMotionModal` をダッシュボード由来コンポーネントとして再利用可能。

### 6.6 Logs（`/logs`）

- `LogsTable` + `useLogs`
- 列: Status / Motion / Action / Camera / Date 等
- Status 表示:
  - `SUCCESS` → Tag success
  - `FAILED` → Tag error
  - `COOLING_DOWN` → Tag warning
- 日時: dayjs 等で人間可読フォーマット（実装依存）
- サーバ側高度フィルタ・ページネーションは限定的（`limit` クエリ中心）

### 6.7 共通: API ステータス

- コンポーネント: `ApiStatusBadge`
- `GET /healthz` を約 10 秒間隔でポーリング（`useApiHealth`）
- 表示: online/offline 相当の Badge + API ベース URL

---

## 7. ディレクトリ構成

```text
front/app/
├── root.tsx                 # ConfigProvider(dark) + QueryProvider
├── app.css                  # Tailwind import + body 背景等
├── routes.ts                # ルート定義
├── components/
│   ├── layout/
│   │   ├── AppLayout.tsx    # default export（layout 必須）
│   │   ├── Sidebar.tsx
│   │   └── Header.tsx
│   ├── common/
│   │   ├── QueryProvider.tsx
│   │   └── BackToDashboard.tsx
│   └── dashboard/
│       ├── SummaryCard.tsx
│       ├── ApiStatusBadge.tsx
│       ├── LogsTable.tsx
│       ├── DeviceBindingPanel.tsx
│       └── NewMotionModal.tsx
├── pages/
│   ├── DashboardPage.tsx
│   ├── MotionsPage.tsx
│   ├── DevicesPage.tsx
│   ├── DeviceDetailPage.tsx
│   ├── BindingsPage.tsx
│   └── LogsPage.tsx
├── routes/                  # RR ルートエントリ（meta 等）
├── hooks/
│   ├── queryKeys.ts
│   ├── useApiHealth.ts
│   ├── useMotions.ts
│   ├── useAppliances.ts
│   ├── useActions.ts
│   ├── useBindings.ts
│   ├── useLogs.ts
│   └── useExecuteAction.ts
├── services/
│   └── backendApiClient.ts
└── types/
    └── backendApi.ts
```

---

## 8. データ取得・状態管理

### 8.1 QueryClient 既定

`QueryProvider` にて概ね次の方針:

- `staleTime`: 数十秒オーダー（実装値に従う）
- `refetchOnWindowFocus`: オフまたは控えめ

### 8.2 クエリキー（`hooks/queryKeys.ts`）

| キー | 用途 |
|---|---|
| `["health"]` | `/healthz` |
| `["cameras"]` | カメラ一覧（クライアントに用意） |
| `["motions"]` | モーション |
| `["appliances"]` | 家電 |
| `["actions", applianceId \| "*"]` | アクション |
| `["bindings"]` | バインディング |
| `["logs", limit]` | ログ |

### 8.3 ミューテーション後の invalidate

| 操作 | invalidate 対象（目安） |
|---|---|
| バインディング作成 | `bindings`（必要なら関連一覧） |
| アクション手動実行 | `logs` |
| 家電作成 | `appliances` |

### 8.4 API クライアント（`backendApiClient.ts`）

| 関数 | 説明 |
|---|---|
| `request<T>(path, init?)` | 共通 `fetch`。JSON、エラー時は `error` フィールドまたは HTTP 文言 |
| `getApiBaseUrl()` | 表示・デバッグ用 |
| `getSnapshot()` | cameras/motions/appliances/actions/bindings/logs を並列取得 |
| `saveBinding(input)` | `POST /api/bindings` |
| `executeAction(actionId)` | `POST /api/actions/:id/execute` |

各フックは `request` または上記関数を `queryFn` / `mutationFn` から呼ぶ。

---

## 9. 型定義（`types/backendApi.ts`）

バックエンド API に追従。主要型:

| 型 | 要点 |
|---|---|
| `Camera` | id, name, streamUrl, location, isEnabled, createdAt |
| `Motion` | id, code, name, description |
| `Appliance` | id, name, category, controlProvider, controllerId?, createdAt |
| `Action` | `providerType` を判別キーにした `TuyaAction | IRAction` |
| `Action.params` | TuyaパラメータまたはESP32_IRのcontrollerId/signal/repeat |
| `MotionBinding` | id, cameraId?, motionId, actionId, isEnabled, createdAt |
| `ActionLog` | status: `SUCCESS` \| `FAILED` \| `COOLING_DOWN` 他 |
| `CreateBindingRequest` | cameraId?, motionId, actionId |
| `ExecuteActionResponse` | success, message? |
| `BackendSnapshot` | 上記コレクションの一括 |

詳細なリクエスト/レスポンス契約は `docs/backend-api-specification.md` および `backend/openapi.yaml` を正とする。

---

## 10. バックエンド連携一覧

フロントが利用するエンドポイント:

| Method | Path | 画面・機能 |
|---|---|---|
| GET | `/healthz` | ApiStatusBadge |
| GET | `/api/cameras` | snapshot 等 |
| GET | `/api/motions` | Motions, フォーム, 表示 join |
| GET | `/api/appliances` | Devices, Sidebar, Detail |
| POST | `/api/appliances` | Devices 登録 |
| GET | `/api/actions` | フォーム, Manual Control, join |
| POST | `/api/actions/:id/execute` | Manual Control |
| GET | `/api/appliances/:id/ir/health` | 赤外線コントローラー状態 |
| POST | `/api/appliances/:id/ir/learn/start` | 赤外線学習開始 |
| GET | `/api/appliances/:id/ir/learn/status` | 赤外線受信ポーリング |
| POST | `/api/appliances/:id/ir/learn/confirm` | 受信信号をActionとして保存 |
| POST | `/api/appliances/:id/ir/learn/stop` | 赤外線学習中止 |
| POST | `/api/appliances/:id/ir/test` | 赤外線LEDテスト |
| GET | `/api/bindings` | Bindings, Detail |
| POST | `/api/bindings` | New Motion / バインディング作成 |
| DELETE | `/api/bindings/:id` | Bindings / バインディング削除 |
| GET | `/api/logs?limit=` | Dashboard, Logs |

認証: 現行フロントは API キー/トークンを付与しない（バックエンドがローカル前提の場合に合わせる）。

---

## 11. 既知の制限・ギャップ

| 項目 | フロントの扱い | 依存 |
|---|---|---|
| `DELETE /api/bindings/:id` | Del の確認後に削除APIを呼び出し、成功後に一覧を再取得 | — |
| `GET /api/appliances/:id` | 一覧フィルタで代替 | BE 任意 |
| ログ confidence / 詳細エラー | フィールドがあれば表示拡張可。現状は API 応答範囲 | BE |
| カメラ死活の高精度表示 | 専用 API なし。既存フィールド頼み | BE / micon |
| リアルタイム更新 | `/api/logs/stream` のSSEをログ表示中だけ購読。切断時は30秒間隔のQuery再取得で補完 | BE |
| モーションマスタ新規作成 | UI は binding 作成が中心 | 仕様 |
| camera 単位のアクション選択 | BE は motion→action 中心。cameraId は optional メタ | `backend-api-specification.md` §1 |
| 仮デモ UI | 専用ルート・welcome・旧 mock は削除済み（`5a89fb4`） | — |

---

## 12. antd v6 実装上の注意

本プロジェクトで特に意識する点:

| コンポーネント | 方針 |
|---|---|
| `Menu` | `items` プロパティ（`Menu.Item` 子要素は使わない） |
| `Statistic` | v6 の styles API に合わせる |
| `Table` | `pagination.placement` 等 v6 API |
| `Modal` | `destroyOnHidden` 等 |
| React 19 | `@ant-design/v5-patch-for-react-19` は不要 |

公式: [Migration to v6](https://ant.design/docs/react/migration-v6)

---

## 13. 非機能要件

| 項目 | 方針 |
|---|---|
| 型安全 | `npm run typecheck` 通過を変更時の最低条件とする |
| ビルド | `npm run build` 通過 |
| シークレット | `.env` をコミットしない（リポジトリ `.gitignore` で `.env` / `.env.*` を除外） |
| アクセシビリティ | antd 既定に依存。カスタム操作はボタンラベルを明確に |
| i18n | UI 文言は日本語混在（現状固定。i18n ライブラリ未導入） |
| ブラウザ | モダン evergreen（ES modules / fetch） |

---

## 14. ローカル結合手順

```bash
# 1. バックエンド（.env は source が必要。Go は自動読込しない）
cd backend
cp -n .env.example .env
set -a && source .env && set +a
go run ./cmd/server
# → http://localhost:8080/healthz が {"status":"ok"} 等

# 2. フロント
cd front
# 任意: echo 'VITE_API_BASE_URL=http://localhost:8080' > .env
npm run dev
# → http://localhost:5173
```

確認観点:

1. ヘッダー API バッジが online
2. Dashboard 件数が API 件数と一致
3. Bindings で作成 → 一覧更新
4. Device Detail の Manual Control で execute → Logs に反映（dry-run 設定時は Tuya 実制御なし）

---

## 15. 変更履歴（ドキュメント）

| 日付 | 内容 |
|---|---|
| 2026-08-06 | 初版。実装済み UI（多ページ・ダーク・手動制御）を仕様として固定 |
