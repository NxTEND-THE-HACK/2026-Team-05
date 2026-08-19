# マイコン側: XIAO ESP32S3 Sense MJPEGカメラ

仕様書のカメラ端末部分を担当するファームウェアです。カメラ画像を保存・解析せず、同一LAN上へHTTP MJPEGとして配信します。Sense拡張基板のPDMマイクは端末内で周囲音より大きな短音だけを検出し、音声や音量を送らずイベントのみをPythonへ通知します。

## エンドポイント

| パス | 用途 |
| --- | --- |
| `/stream` | Pythonワーカー向けのMJPEGストリーム |
| `/snapshot` | 1枚のJPEG。設置確認用 |
| `/health` | `camera_id`、Wi-Fi状態、IP、稼働時間、最大FPS、マイク準備状態を返す |
| `/` | エンドポイントの案内 |

音イベントは長時間の映像配信と競合しないよう、別ポートで配信します。

| URL | 用途 |
| --- | --- |
| `http://<IP>:81/sound-events` | Python向けNDJSON音イベント／heartbeat |

音イベントは `{"type":"sound","sequence":12,"uptime_ms":34567}`、1秒ごとの生存確認は `{"type":"heartbeat","uptime_ms":34567}` の形式です。PCM、音量、周囲ノイズ値は送信も保存もしません。再接続前の古いイベントは再送しません。

## 開発環境

- PlatformIO
- Seeed Studio XIAO ESP32S3 Sense
- Arduino framework / `seeed_xiao_esp32s3`
- 115200 baud

公式のカメラ配線に合わせたGPIO定義は `include/camera_pins.h` にまとめています。マイクはGPIO42（PDM CLK）とGPIO41（PDM DATA）を使います。PSRAMが利用できる場合はJPEGフレームバッファを2枚使い、遅延したフレームではなく最新フレームを優先します。高画質設定は800×600（SVGA）、JPEG品質8、最大15 FPSです。負荷や遅延が大きい場合は `config.h` で640×480または320×240へ下げられます。

## セットアップ

```powershell
cd micon
Copy-Item include/config.h.example include/config.h
```

`include/config.h` を編集し、Wi-Fi情報とカメラごとの `CAMERA_ID` を設定します。2台目は `demo-camera-2` など別のIDにしてください。

音検出は起動後2秒間に周囲音を学習し、その基準より十分大きな短音を1イベントとして扱います。感度、解除倍率、クールダウンは `SOUND_*` 設定で調整できます。学習中はできるだけ通常の室内音を保ってください。

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

シリアルモニターに表示されたIPを使い、`http://<IP>/health`、`http://<IP>/stream`、`http://<IP>:81/sound-events` を確認します。Python側のURLは次の形式です。

```text
http://<camera-ip>/stream
http://<camera-ip>:81/sound-events
```

詳しい確認項目は `test/test.md` を参照してください。
