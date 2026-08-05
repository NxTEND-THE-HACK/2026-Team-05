## マイコン側の手動テスト

### ビルド前

1. `micon/include/config.h.example` を `micon/include/config.h` にコピーする。
2. `WIFI_SSID`、`WIFI_PASSWORD` を設定する。
3. 1台目は `CAMERA_ID` を `demo-camera-1`、2台目は `demo-camera-2` にする。
4. XIAO ESP32S3 Sense にカメラ拡張ボードとアンテナを取り付ける。

### 書き込み

```powershell
cd micon
pio run -t upload
pio device monitor
```

### 疎通確認

シリアルモニターに表示されたIPアドレスを `CAMERA_IP` とする。

```powershell
curl.exe http://CAMERA_IP/health
curl.exe http://CAMERA_IP/snapshot --output snapshot.jpg
```

`http://CAMERA_IP/stream` をブラウザまたはPythonワーカーから開き、MJPEGが連続表示されることを確認する。

### 障害確認

- Wi-Fiを一度切断し、5秒間隔で再接続を試みること。
- `/health` の `camera_id` が2台で異なること。
- Pythonワーカーを切断しても、カメラがリセットせず待機すること。
- 映像ファイルがSDカードやフラッシュへ保存されていないこと。
