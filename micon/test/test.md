## マイコン側の手動テスト

### ビルド前

1. `micon/include/config.h.example` を `micon/include/config.h` にコピーする。
2. `WIFI_SSID`、`WIFI_PASSWORD` を設定する。
3. 1台目は `CAMERA_ID` を `demo-camera-1`、2台目は `demo-camera-2` にする。
4. 固定IPを使う場合は `CAMERA_USE_STATIC_IP=1` とし、2台で異なるIPを設定する。DHCP範囲との重複がないことを確認する。
5. XIAO ESP32S3 Sense にカメラ拡張ボードとアンテナを取り付ける。

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
`/health` の `camera_frame_ready` が `true` になり、`/stream` を2クライアント以上から同時に開いても各クライアントへフレームが届くことを確認する。PowerShellでは次のように2本を同時起動できる。

```powershell
Start-Job { curl.exe -N http://CAMERA_IP/stream --output stream-1.mjpeg }
Start-Job { curl.exe -N http://CAMERA_IP/stream --output stream-2.mjpeg }
curl.exe http://CAMERA_IP/health
curl.exe http://CAMERA_IP/snapshot --output snapshot-concurrent.jpg
```

### 障害確認

- Wi-Fiを一度切断し、5秒間隔で再接続を試みること。
- `/health` の `camera_id` が2台で異なること。
- 固定IPを有効にした場合、シリアルログのIPが設定値と一致すること。
- Pythonワーカーを切断しても、カメラがリセットせず待機すること。
- カメラフレームが未取得の場合、`/snapshot` と最初の `/stream` が無限待ちにならず、一定時間後に `503 Service Unavailable` を返すこと。
- `/health` の `camera_frame_ready` が、カメラ取得停止後に古いフレームのまま `true` になり続けないこと。
- カメラ取得タスクを停止させた場合、`CAMERA_CAPTURE_WATCHDOG_TIMEOUT_MS` 経過後に自動再起動して復旧すること。
- 映像ファイルがSDカードやフラッシュへ保存されていないこと。
