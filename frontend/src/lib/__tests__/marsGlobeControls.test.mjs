import test from "node:test";
import assert from "node:assert/strict";

import {
  applyMarsGlobeControllerConfig,
  clampZoomStepMeters,
  CLICK_DRAG_THRESHOLD_PX,
  formatCursorReadout,
  isDragGesture,
  MARS_GLOBE_CAMERA_LIMITS,
  MARS_GLOBE_CONTROLLER_CONFIG,
  normalizeLongitudeEast360,
} from "../marsGlobeControls.ts";

test("Shared Mars Globe Controls & Interaction Helpers", async (t) => {
  await t.test("click-vs-drag separates genuine clicks from drags and flicks", () => {
    assert.equal(isDragGesture({ x: 100, y: 100 }, { x: 102, y: 102 }, 2.8), false);
    assert.equal(
      isDragGesture({ x: 100, y: 100 }, { x: 100 + CLICK_DRAG_THRESHOLD_PX + 1, y: 100 }, 6),
      true
    );
    // Returning to start position after dragging out still counts as a drag
    assert.equal(isDragGesture({ x: 100, y: 100 }, { x: 101, y: 100 }, 24), true);
  });

  await t.test("normalizes longitude across 180-degree antimeridian continuously", () => {
    assert.equal(normalizeLongitudeEast360(-180), 180);
    assert.equal(normalizeLongitudeEast360(-1), 359);
    assert.equal(normalizeLongitudeEast360(361), 1);
    assert.equal(formatCursorReadout(-4.74, -222.595), "CURSOR: -4.7400°, 137.4050° E");
  });

  await t.test("clamps zoom steps within minimum and maximum Mars camera altitudes", () => {
    const nearGround = clampZoomStepMeters(MARS_GLOBE_CAMERA_LIMITS.minZoomDistanceM, 0.6);
    assert.equal(nearGround.direction, "in");
    assert.equal(nearGround.stepM, 0);

    const farSpace = clampZoomStepMeters(MARS_GLOBE_CAMERA_LIMITS.maxZoomDistanceM, 1.6);
    assert.equal(farSpace.direction, "out");
    assert.equal(farSpace.stepM, 0);

    const midZoom = clampZoomStepMeters(500_000, 0.6);
    assert.equal(midZoom.direction, "in");
    assert.ok(midZoom.stepM > 0 && midZoom.stepM < 500_000);
  });

  await t.test("applies coherent ScreenSpaceCameraController inertia and zoom settings", () => {
    const fakeController = {
      minimumZoomDistance: 0,
      minimumCollisionTerrainHeight: 0,
      maximumZoomDistance: 0,
      inertiaSpin: 0,
      inertiaTranslate: 0,
      inertiaZoom: 0,
      zoomFactor: 0,
      enableCollisionDetection: false,
      enableRotate: false,
      enableTranslate: false,
      enableZoom: false,
      enableTilt: false,
      enableLook: true,
    };
    applyMarsGlobeControllerConfig(fakeController);
    assert.equal(fakeController.inertiaSpin, MARS_GLOBE_CONTROLLER_CONFIG.inertiaSpin);
    assert.equal(fakeController.inertiaTranslate, MARS_GLOBE_CONTROLLER_CONFIG.inertiaTranslate);
    assert.equal(fakeController.inertiaZoom, MARS_GLOBE_CONTROLLER_CONFIG.inertiaZoom);
    assert.equal(fakeController.zoomFactor, MARS_GLOBE_CONTROLLER_CONFIG.zoomFactor);
    assert.equal(fakeController.enableLook, false);
    assert.equal(fakeController.minimumZoomDistance, MARS_GLOBE_CAMERA_LIMITS.minZoomDistanceM);
    assert.equal(fakeController.maximumZoomDistance, MARS_GLOBE_CAMERA_LIMITS.maxZoomDistanceM);
  });
});
