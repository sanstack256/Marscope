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

export function toLongitude180(lonDeg: number): number {
  if (lonDeg === 360) return 180;
  if (lonDeg > 180) return ((lonDeg + 180) % 360) - 180;
  if (lonDeg < -180) return ((lonDeg - 180) % 360) + 180;
  return lonDeg;
}

/**
 * Sanitize GeoJSON Polygon / MultiPolygon outer rings for Cesium globe rendering.
 * Rejects global >=350-degree boxes and antimeridian-wrapping chords that extend beyond the globe limb.
 */
export function sanitizeGlobePolygonRings(
  geom: { type?: string; coordinates?: unknown } | null | undefined
): Array<Array<[number, number]>> {
  if (!geom || !geom.coordinates) return [];

  const toRing = (coords: unknown): Array<[number, number]> => {
    if (!Array.isArray(coords)) return [];
    const pts: Array<[number, number]> = [];
    let rawMinLon = Infinity;
    let rawMaxLon = -Infinity;
    for (const c of coords) {
      if (
        Array.isArray(c) &&
        c.length >= 2 &&
        typeof c[0] === "number" &&
        typeof c[1] === "number" &&
        Number.isFinite(c[0]) &&
        Number.isFinite(c[1])
      ) {
        if (c[0] < rawMinLon) rawMinLon = c[0];
        if (c[0] > rawMaxLon) rawMaxLon = c[0];
        const lon = toLongitude180(c[0]);
        const lat = Math.max(-89.9999, Math.min(89.9999, c[1]));
        const prev = pts[pts.length - 1];
        if (!prev || Math.abs(prev[0] - lon) > 1e-7 || Math.abs(prev[1] - lat) > 1e-7) {
          pts.push([lon, lat]);
        }
      }
    }
    if (pts.length < 3) return [];
    if (rawMaxLon - rawMinLon >= 350) {
      return [];
    }

    for (let i = 1; i < pts.length; i += 1) {
      if (Math.abs(pts[i][0] - pts[i - 1][0]) > 180) {
        return [];
      }
    }
    return pts;
  };

  if (geom.type === "Polygon" && Array.isArray(geom.coordinates)) {
    const outer = toRing((geom.coordinates as unknown[])[0]);
    return outer.length >= 3 ? [outer] : [];
  }
  if (geom.type === "MultiPolygon" && Array.isArray(geom.coordinates)) {
    const rings: Array<Array<[number, number]>> = [];
    for (const poly of geom.coordinates as unknown[]) {
      if (Array.isArray(poly)) {
        const outer = toRing(poly[0]);
        if (outer.length >= 3) rings.push(outer);
      }
    }
    return rings;
  }
  return [];
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
