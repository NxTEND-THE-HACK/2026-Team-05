CREATE TABLE IF NOT EXISTS cameras (
    id text PRIMARY KEY,
    name text NOT NULL,
    stream_url text NOT NULL DEFAULT '',
    location text NOT NULL DEFAULT '',
    is_enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS motions (
    id text PRIMARY KEY,
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    description text NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS appliances (
    id text PRIMARY KEY,
    name text NOT NULL,
    category text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS appliance_actions (
    id text PRIMARY KEY,
    appliance_id text NOT NULL REFERENCES appliances(id) ON DELETE CASCADE,
    name text NOT NULL,
    provider_type text NOT NULL,
    params jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS motion_bindings (
    id text PRIMARY KEY,
    camera_id text REFERENCES cameras(id) ON DELETE SET NULL,
    motion_id text NOT NULL REFERENCES motions(id) ON DELETE CASCADE,
    action_id text NOT NULL REFERENCES appliance_actions(id) ON DELETE CASCADE,
    is_enabled boolean NOT NULL DEFAULT true,
    last_executed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (motion_id)
);

CREATE TABLE IF NOT EXISTS processed_events (
    event_id text PRIMARY KEY,
    received_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS action_logs (
    id text PRIMARY KEY,
    event_id text NOT NULL,
    camera_id text NOT NULL,
    camera_name text NOT NULL DEFAULT '',
    motion_code text NOT NULL,
    motion_name text NOT NULL DEFAULT '',
    action_id text,
    action_name text NOT NULL DEFAULT '',
    status text NOT NULL CHECK (status IN ('SUCCESS', 'FAILED', 'COOLING_DOWN')),
    error_message text NOT NULL DEFAULT '',
    detected_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS action_logs_created_at_idx ON action_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS action_logs_event_id_idx ON action_logs (event_id);

INSERT INTO cameras (id, name, location) VALUES
    ('demo-camera-1', 'カメラ1', 'デモエリア1'),
    ('demo-camera-2', 'カメラ2', 'デモエリア2')
ON CONFLICT (id) DO NOTHING;

INSERT INTO motions (id, code, name, description) VALUES
    ('motion-pose-right-hand-up', 'POSE_RIGHT_HAND_UP', '右手上げ', '右手首を右肩より上で0.6秒保持'),
    ('motion-swipe-right', 'MOTION_SWIPE_RIGHT', '右スワイプ', '右手を右方向へスワイプ')
ON CONFLICT (id) DO NOTHING;

INSERT INTO appliances (id, name, category) VALUES
    ('appliance-plug-a', 'スマートプラグA', 'スマートプラグ'),
    ('appliance-plug-b', 'スマートプラグB', 'スマートプラグ'),
    ('appliance-plug-c', 'スマートプラグC', 'スマートプラグ')
ON CONFLICT (id) DO NOTHING;

INSERT INTO appliance_actions (id, appliance_id, name, provider_type, params) VALUES
    ('action-plug-a-on', 'appliance-plug-a', 'プラグA オン', 'TUYA', '{"deviceIdEnv":"PLUG_A_ID","switchCode":"switch","value":true}'),
    ('action-plug-a-off', 'appliance-plug-a', 'プラグA オフ', 'TUYA', '{"deviceIdEnv":"PLUG_A_ID","switchCode":"switch","value":false}'),
    ('action-plug-b-on', 'appliance-plug-b', 'プラグB オン', 'TUYA', '{"deviceIdEnv":"PLUG_B_ID","switchCode":"switch","value":true}'),
    ('action-plug-b-off', 'appliance-plug-b', 'プラグB オフ', 'TUYA', '{"deviceIdEnv":"PLUG_B_ID","switchCode":"switch","value":false}'),
    ('action-plug-c-on', 'appliance-plug-c', 'プラグC オン', 'TUYA', '{"deviceIdEnv":"PLUG_C_ID","switchCode":"switch","value":true}'),
    ('action-plug-c-off', 'appliance-plug-c', 'プラグC オフ', 'TUYA', '{"deviceIdEnv":"PLUG_C_ID","switchCode":"switch","value":false}')
ON CONFLICT (id) DO NOTHING;
