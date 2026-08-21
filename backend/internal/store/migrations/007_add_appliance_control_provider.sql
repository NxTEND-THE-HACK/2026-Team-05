ALTER TABLE appliances
    ADD COLUMN IF NOT EXISTS control_provider text NOT NULL DEFAULT 'TUYA',
    ADD COLUMN IF NOT EXISTS controller_id text NOT NULL DEFAULT '';

UPDATE appliances
SET control_provider = 'TUYA'
WHERE control_provider = '';
