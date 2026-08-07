INSERT INTO motions (id, code, name, description) VALUES
    ('motion-hand-rotate-right', 'MOTION_HAND_ROTATE_RIGHT', '右回し', '右手の手のひらを基準から時計回りに30度以上回す'),
    ('motion-hand-rotate-left', 'MOTION_HAND_ROTATE_LEFT', '左回し', '左手の手のひらを基準から反時計回りに30度以上回す')
ON CONFLICT (id) DO NOTHING;
