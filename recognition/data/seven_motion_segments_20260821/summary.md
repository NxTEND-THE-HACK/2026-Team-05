# MediaPipeランドマーク分割結果

入力: `data\seven_motion_raw_collection_20260821.jsonl`
出力: `data\seven_motion_segments_20260821`

## 確認結果

- rawフレーム数: 5110
- パー区切り: 42回
- 作成セグメント: 41個
- 6種類×10回を満たす: いいえ

| 動作 | セグメント数 | フレーム数 |
|---|---:|---:|
| 右手上げ (`POSE_RIGHT_HAND_UP`) | 10 | 1653 |
| 左手上げ (`POSE_LEFT_HAND_UP`) | 10 | 1421 |
| 右スワイプ (`MOTION_SWIPE_RIGHT`) | 10 | 441 |
| 左スワイプ (`MOTION_SWIPE_LEFT`) | 10 | 433 |
| Goodから上 (`MOTION_THUMBS_UP_MOVE_UP`) | 1 | 49 |
| Badから下 (`MOTION_THUMBS_DOWN_MOVE_DOWN`) | 0 | 0 |
| 指パッチン (`MOTION_FINGER_SNAP`) | 0 | 0 |

各セグメントは `動作コード/sample_01.jsonl` の形式で保存しています。
`all_segments.jsonl` は全セグメントをまとめたファイル、`manifest.json` は区切り位置と検証結果です。
