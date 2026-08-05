# マイコン側: XIAO ESP32S3 Sense MJPEGカメラ

仕様書のカメラ端末部分を担当するファームウェアです。カメラ画像を保存・解析せず、同一LAN上へHTTP MJPEGとして配信します。

## エンドポイント

| パス | 用途 |
| --- | --- |
| `/stream` | Pythonワーカー向けのMJPEGストリーム |
| `/snapshot` | 1枚のJPEG。設置確認用 |
| `/health` | `camera_id`、Wi-Fi状態、IP、稼働時間を返す |
| `/` | エンドポイントの案内 |

## 開発環境

- PlatformIO
- Seeed Studio XIAO ESP32S3 Sense
- Arduino framework / `seeed_xiao_esp32s3`
- 115200 baud

公式のカメラ配線に合わせたGPIO定義は `include/camera_pins.h` にまとめています。PSRAMが利用できる場合はJPEGフレームバッファを2枚使い、遅延したフレームではなく最新フレームを優先します。高画質設定は800×600（SVGA）、JPEG品質8です。負荷や遅延が大きい場合は `config.h` で640×480または320×240へ下げられます。

## セットアップ

```powershell
cd micon
Copy-Item include/config.h.example include/config.h
```

`include/config.h` を編集し、Wi-Fi情報とカメラごとの `CAMERA_ID` を設定します。2台目は `demo-camera-2` など別のIDにしてください。

固定IPをデバイス側で使う場合は、`CAMERA_USE_STATIC_IP` を `1` にし、
`CAMERA_STATIC_IP`、`CAMERA_GATEWAY`、`CAMERA_SUBNET`、DNSを設定します。
2台の固定IPは重複させず、ルーターのDHCP割り当て範囲外から選んでください。
設定例では1台目を `192.168.10.105`、2台目を `192.168.10.106` にしています。
固定IP設定に失敗した場合、シリアルログにエラーを出してWi-Fi接続を再試行します。

```powershell
pio run
pio run -t upload
pio device monitor
```

シリアルモニターに表示されたIPを使い、`http://<IP>/health` と `http://<IP>/stream` を確認します。Python側のストリームURLは次の形式です。

```text
http://<camera-ip>/stream
```

詳しい確認項目は `test/test.md` を参照してください。
