INSERT INTO motions (id, code, name, description) VALUES
    ('motion-finger-snap', 'MOTION_FINGER_SNAP', '指パッチン', '右手を曲げた準備姿勢から人差し指を伸ばす')
ON CONFLICT (id) DO NOTHING;
