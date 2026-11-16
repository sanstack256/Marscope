export interface ScreenPosition2D {
  x: number;
  y: number;
}

export interface MarsGlobeCameraLimits {
  globalHeightM: number;
  minZoomDistanceM: number;
  maxZoomDistanceM: number;
  minCollisionTerrainHeightM: number;
}

export interface MarsGlobeControllerConfig {
  inertiaSpin: number;
  inertiaTranslate: number;
  inertiaZoom: number;
  zoomFactor: number;
  enableRotate: boolean;
  enableTranslate: boolean;
  enableZoom: boolean;
  enableTilt: boolean;
  enableLook: boolean;
  enableCollisionDetection: boolean;
}

export const CLICK_DRAG_THRESHOLD_PX = 5;

export const MARS_GLOBE_CAMERA_LIMITS: MarsGlobeCameraLimits = {
  globalHeightM: 9_000_000,
  minZoomDistanceM: 120,
  maxZoomDistanceM: 22_000_000,
  minCollisionTerrainHeightM: 120,
};

export const MARS_GLOBE_CONTROLLER_CONFIG: MarsGlobeControllerConfig = {
  inertiaSpin: 0.9,
  inertiaTranslate: 0.9,
  inertiaZoom: 0.8,
  zoomFactor: 2.6,
  enableRotate: true,
  enableTranslate: true,
  enableZoom: true,
  enableTilt: true,
  enableLook: false,
  enableCollisionDetection: true,
};

export function computePointerTravelPx(a: ScreenPosition2D, b: ScreenPosition2D): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

/**
 * Distinguish a genuine surface click from a camera drag or flick.
 * Any gesture whose maximum pointer travel exceeds thresholdPx is treated as a drag.
 */
export function isDragGesture(
  downPos: ScreenPosition2D | null,
  upPos: ScreenPosition2D | null,
  maxTravelPx: number,
  thresholdPx: number = CLICK_DRAG_THRESHOLD_PX
): boolean {
  if (!downPos || !upPos) return maxTravelPx > thresholdPx;
  const endTravel = computePointerTravelPx(downPos, upPos);
  return Math.max(maxTravelPx, endTravel) > thresholdPx;
}

export function normalizeLongitudeEast360(lonDeg: number): number {
  return ((lonDeg % 360) + 360) % 360;
}

export function formatCursorReadout(latDeg: number, lonDeg: number): string {
  const lonEast = normalizeLongitudeEast360(lonDeg);
  return `CURSOR: ${latDeg.toFixed(4)}°, ${lonEast.toFixed(4)}° E`;
}

export function clampZoomStepMeters(
  currentHeightM: number,
  factor: number,
  limits: MarsGlobeCameraLimits = MARS_GLOBE_CAMERA_LIMITS
): { direction: "in" | "out"; stepM: number } {
  const safeHeight = Math.max(limits.minZoomDistanceM, currentHeightM);
  if (factor < 1) {
    const rawStep = Math.max(25, safeHeight * (1.0 - factor));
    const maxAllowed = Math.max(0, safeHeight - limits.minZoomDistanceM);
    return { direction: "in", stepM: Math.min(maxAllowed, rawStep) };
  }
  const rawStep = Math.max(50, safeHeight * (factor - 1.0));
  const maxAllowed = Math.max(0, limits.maxZoomDistanceM - safeHeight);
  return { direction: "out", stepM: Math.min(maxAllowed, rawStep) };
}

export interface CesiumScreenSpaceControllerLike {
  minimumZoomDistance: number;
  minimumCollisionTerrainHeight: number;
  maximumZoomDistance: number;
  inertiaSpin: number;
  inertiaTranslate: number;
  inertiaZoom: number;
  zoomFactor: number;
  enableCollisionDetection: boolean;
  enableRotate: boolean;
  enableTranslate: boolean;
  enableZoom: boolean;
  enableTilt: boolean;
  enableLook: boolean;
}

export function applyMarsGlobeControllerConfig(
  controller: CesiumScreenSpaceControllerLike,
  limits: MarsGlobeCameraLimits = MARS_GLOBE_CAMERA_LIMITS,
  config: MarsGlobeControllerConfig = MARS_GLOBE_CONTROLLER_CONFIG
): void {
  controller.minimumZoomDistance = limits.minZoomDistanceM;
  controller.minimumCollisionTerrainHeight = limits.minCollisionTerrainHeightM;
  controller.maximumZoomDistance = limits.maxZoomDistanceM;
  controller.inertiaSpin = config.inertiaSpin;
  controller.inertiaTranslate = config.inertiaTranslate;
  controller.inertiaZoom = config.inertiaZoom;
  controller.zoomFactor = config.zoomFactor;
  controller.enableCollisionDetection = config.enableCollisionDetection;
  controller.enableRotate = config.enableRotate;
  controller.enableTranslate = config.enableTranslate;
  controller.enableZoom = config.enableZoom;
  controller.enableTilt = config.enableTilt;
  controller.enableLook = config.enableLook;
}
