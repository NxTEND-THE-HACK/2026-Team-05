INSERT INTO motions (id, code, name, description) VALUES
    ('motion-pose-left-hand-up', 'POSE_LEFT_HAND_UP', '左手上げ', '左手首を左肩より上で0.45秒保持'),
    ('motion-swipe-left', 'MOTION_SWIPE_LEFT', '左スワイプ', '左手を左方向へスワイプ'),
    ('motion-thumbs-up-move-up', 'MOTION_THUMBS_UP_MOVE_UP', 'Goodから上', '右手を親指上の状態にして上へ動かす'),
    ('motion-thumbs-down-move-down', 'MOTION_THUMBS_DOWN_MOVE_DOWN', 'Badから下', '右手を親指下の状態にして下へ動かす'),
    ('motion-clap', 'MOTION_CLAP', '拍手', '左右の手を離した状態から近づけて叩く'),
    ('motion-open-to-fist-down', 'MOTION_OPEN_TO_FIST_DOWN', 'パーからグーで下げる', '右手をパーからグーにしながら下へ動かす')
ON CONFLICT (id) DO NOTHING;
