# 2026 Team-05

ジェスチャーで家電を操作するスマートホーム MVP。最新の開発ブランチは `develop`。

## 構成

| ディレクトリ | 役割 | ポート |
| --- | --- | --- |
| `backend` | Go API。認識イベントを受けてTuyaプラグを操作 | 8080 |
| `front` | React Router 管理画面 | 5173 |
| `recognition` | Python ジェスチャー認識ワーカー(カメラごとに1プロセス) | — |
| `micon` | ESP32カメラのファームウェア(実機で動作。PCからは起動しない) | — |

## 一括起動

```bash
./dev.sh
```

backend / front / recognition をまとめて起動します。停止は `Ctrl+C` で全サービスが終了します。ログはターミナルに色付きで表示されるほか、`logs/` にも保存されます。

ポート 8080 / 5173 を他プロジェクトの Docker コンテナが使っている場合は、自動で `docker stop` してから起動します。

オプション:

```bash
./dev.sh --no-recognition  # 認識ワーカーなし(カメラ不要の開発向け)
./dev.sh --no-front        # フロントなし
./dev.sh --no-backend      # バックエンドなし
./dev.sh --no-open         # ブラウザを自動で開かない
```

## 初回セットアップ

```bash
./setup.sh
```

`setup.sh` は次を自動で実行します。

- `backend/.env` を `.env.example` から作成(既存ファイルは上書きしない)
- Goモジュールのダウンロード
- `front` のnpm依存関係のインストール
- `recognition/.venv` の作成とPython依存関係のインストール
- MediaPipeモデルのダウンロード

Go / Node.js / Python 3.11以降の本体は事前に必要です。macOSの場合は次の例でインストールできます。

```bash
brew install go node python@3.11
```

`recognition/.env` の `CAMERA_SOURCE` にはマイコンのIPを指定します。初期値は `http://192.168.10.106/stream` です。`CAMERA_ID` はバックエンドの初期データ `demo-camera-1` / `demo-camera-2` と合わせてください。

各サービスの詳細はそれぞれの README(`backend/README.md`、`front/README.md`、`recognition/README.md`、`micon/README.md`)を参照してください。
