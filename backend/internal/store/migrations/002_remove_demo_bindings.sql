-- Camera IDs identify recognition sources/rooms. They must not imply a device.
-- Remove the provisional camera-to-plug assignments if 001 was applied earlier.
DELETE FROM motion_bindings
WHERE id IN (
    'binding-camera-1-on',
    'binding-camera-1-off',
    'binding-camera-2-on',
    'binding-camera-2-off'
);
