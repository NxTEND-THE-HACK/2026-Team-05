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
# backend
cd backend && cp .env.example .env   # Tuya接続情報などを編集

# front
cd front && npm install

# recognition
cd recognition
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python scripts/download_models.py --output-dir models
cp .env.example .env                 # CAMERA_ID / CAMERA_SOURCE を実機に合わせて編集
```

`recognition/.env` の `CAMERA_SOURCE` にはマイコンのIPを指定します(例: `http://192.168.10.106/stream`)。`CAMERA_ID` はバックエンドの初期データ `demo-camera-1` / `demo-camera-2` と合わせてください。

各サービスの詳細はそれぞれの README(`backend/README.md`、`front/README.md`、`recognition/README.md`、`micon/README.md`)を参照してください。
