-- A motion selects an action globally. Camera IDs are retained as optional
-- metadata for future room-specific behavior, but are not part of uniqueness.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'motion_bindings'
          AND column_name = 'camera_id'
    ) THEN
        -- Camera-specific bindings cannot be translated unambiguously. Retain one
        -- deterministic binding per motion before removing the camera dimension.
        DELETE FROM motion_bindings newer
        USING motion_bindings older
        WHERE newer.motion_id = older.motion_id
          AND (newer.created_at, newer.id) > (older.created_at, older.id);

        ALTER TABLE motion_bindings
            DROP CONSTRAINT IF EXISTS motion_bindings_camera_id_motion_id_key;
        ALTER TABLE motion_bindings
            DROP CONSTRAINT IF EXISTS motion_bindings_camera_id_fkey;
        ALTER TABLE motion_bindings ALTER COLUMN camera_id DROP NOT NULL;
        ALTER TABLE motion_bindings
            ADD CONSTRAINT motion_bindings_camera_id_fkey
            FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE SET NULL;
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS motion_bindings_motion_id_key
    ON motion_bindings (motion_id);
