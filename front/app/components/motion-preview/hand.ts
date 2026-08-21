export interface HandPose {
  thumb: number;
  index: number;
  middle: number;
  ring: number;
  pinky: number;
  thumbTilt: number;
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function handPose(partial: Partial<HandPose> = {}): HandPose {
  return {
    thumb: 0,
    index: 0,
    middle: 0,
    ring: 0,
    pinky: 0,
    thumbTilt: 0,
    ...partial,
  };
}

export const HAND_OPEN: HandPose = handPose();

export const HAND_FIST: HandPose = handPose({
  thumb: 1,
  index: 1,
  middle: 1,
  ring: 1,
  pinky: 1,
});

export const HAND_POINT: HandPose = handPose({
  thumb: 1,
  index: 0,
  middle: 1,
  ring: 1,
  pinky: 1,
});

export const HAND_THUMB_UP: HandPose = handPose({
  thumb: 0,
  index: 1,
  middle: 1,
  ring: 1,
  pinky: 1,
  thumbTilt: Math.PI / 2,
});

export const HAND_THUMB_DOWN: HandPose = handPose({
  thumb: 0,
  index: 1,
  middle: 1,
  ring: 1,
  pinky: 1,
  thumbTilt: -Math.PI / 2,
});

export function lerpHandPose(a: HandPose, b: HandPose, t: number): HandPose {
  return {
    thumb: lerp(a.thumb, b.thumb, t),
    index: lerp(a.index, b.index, t),
    middle: lerp(a.middle, b.middle, t),
    ring: lerp(a.ring, b.ring, t),
    pinky: lerp(a.pinky, b.pinky, t),
    thumbTilt: lerp(a.thumbTilt, b.thumbTilt, t),
  };
}
