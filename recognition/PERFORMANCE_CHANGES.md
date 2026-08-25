# 判定処理FPS改善：変更内容

## 概要

MediaPipe判定モニターの処理速度を改善した。

主な原因はMediaPipeの推論処理そのものではなく、MJPEGストリームから最新フレームを判定ループへ渡す部分でフレームがバースト状に到着し、複数フレームが短時間で上書きされていたことだった。

## 改善前の状態

| 項目 | 実測値 |
| --- | ---: |
| カメラ受信FPS | 約24〜25 FPS |
| 判定処理FPS | 約10〜11 FPS |
| フレーム欠落率 | 約44% |
| MediaPipe検出エラー | 0件 |

カメラは約25FPSで受信できていたが、判定ループが取得できるフレームは約10FPSに留まっていた。

## 実施した変更

### 1. MJPEGフレーム受け渡しの改善

対象：[mjpeg.py](src/gesture_recognition/stream/mjpeg.py)

- MJPEGの読み込みチャンクサイズを64KBから8KBへ変更。
- 1回のソケット読み込みで複数JPEGが連続処理されることを防ぎ、フレーム到着を滑らかにした。
- フレームを最新フレームバッファへ格納した後、1msだけ他スレッドへ処理を譲るようにした。

### 2. フレーム取得ポーリングの短縮

対象：[config.py](src/gesture_recognition/config.py)、[monitor_detections.py](scripts/monitor_detections.py)

- フレームがない場合の待機時間を10msから1msへ変更。
- MJPEGの短い到着間隔を判定ループが取りこぼさないようにした。

### 3. オーバーレイ生成の非同期化

対象：[monitor_detections.py](scripts/monitor_detections.py)

- MediaPipeランドマーク画像のJPEG生成・保存を別スレッドへ移動。
- 未処理の画像をキューに貯めず、常に最新フレームだけを保持。
- オーバーレイの書き込みは既定で最大5FPSに制限。
- 表示画像の更新が判定処理を停止させないようにした。
- `--overlay-fps` で表示更新頻度を変更できる。

### 4. DTW分類処理の軽量化

対象：[temporal.py](src/gesture_recognition/gestures/temporal.py)

- NumPyの座標・重み配列を`float64`から`float32`へ変更。
- テンプレートのDTW計算を大きなバッチで処理。
- 判定条件、判定ウィンドウ、モーションの認識ルールは変更していない。

ベンチマークでは、テンプレート110件の分類時間が約56msから約28msへ短縮された。

### 5. 判定ループ全体のメトリクス追加

対象：[metrics.py](src/gesture_recognition/observability/metrics.py)、[monitor_dashboard.html](monitor_dashboard.html)

MediaPipe検出時間だけでなく、以下も記録・表示するようにした。

- 判定ループFPS
- 判定ループ平均処理時間
- MediaPipe平均処理時間
- フレーム欠落数と処理率

## 改善後の実測値

マイコン`10.0.1.106`のMJPEGストリームで確認した。

| 項目 | 実測値 |
| --- | ---: |
| カメラ受信FPS | 約23.7〜25.7 FPS |
| 判定処理FPS | 約24.6 FPS |
| フレーム欠落 | 8枚 |
| 処理率 | 約99.3% |
| 判定ループ平均時間 | 約19.2ms |
| MediaPipeエラー | 0件 |

## テスト結果

```text
68 passed
```

以下も確認済み。

- Pythonソースのコンパイル確認
- `git diff --check`
- カメラ受信単体：約24FPS
- MediaPipe検出単体：約20FPS以上
- 修正後の判定モニター：約24FPS

## 起動状態

- 判定モニター：起動中
- 判定画面：http://127.0.0.1:8765/monitor_dashboard.html
- Go APIへのイベント配信：無効化したモニターで確認
- コミット：未作成

`recognition/data/` と `recognition/logs/` は実行時に生成された未追跡ファイルであり、今回コミットしていない。
