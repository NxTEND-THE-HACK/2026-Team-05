# MediaPipeランドマーク分割結果

入力: `data\mediapipe_raw_20260819.jsonl`
出力: `data\landmark_segments_20260819`

## 確認結果

- rawフレーム数: 5520
- パー区切り: 61回
- 作成セグメント: 60個
- 6種類×10回を満たす: はい

| 動作 | セグメント数 | フレーム数 |
|---|---:|---:|
| 右手上げ (`POSE_RIGHT_HAND_UP`) | 10 | 647 |
| 左手上げ (`POSE_LEFT_HAND_UP`) | 10 | 596 |
| 右スワイプ (`MOTION_SWIPE_RIGHT`) | 10 | 553 |
| 左スワイプ (`MOTION_SWIPE_LEFT`) | 10 | 543 |
| Goodから上 (`MOTION_THUMBS_UP_MOVE_UP`) | 10 | 571 |
| Badから下 (`MOTION_THUMBS_DOWN_MOVE_DOWN`) | 10 | 583 |

各セグメントは `動作コード/sample_01.jsonl` の形式で保存しています。
`all_segments.jsonl` は全セグメントをまとめたファイル、`manifest.json` は区切り位置と検証結果です。
