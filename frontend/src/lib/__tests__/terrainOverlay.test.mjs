import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  buildTileTextureUrlStrict,
  isOrthoOverlayAvailable,
  OverlayUnavailableError,
  resolveOverlayForManifest,
} from "../terrainOverlay.ts";

const baseTile = {
  bounds: {
    min_lat: -4.85,
    max_lat: -4.75,
    min_lon: 137.38,
    max_lon: 137.44,
  },
};

const manifestWithOrtho = {
  dataset_id: "hirise_dteec_009149_1750",
  ortho_dataset_id: "hirise_psp_009149_1750_ortho",
  elevation_range_m: { min_m: -4520, max_m: -4180 },
  roughness_range_m: { min_m: 0.1, max_m: 4.5 },
};

const manifestWithoutOrtho = {
  dataset_id: "hirise_dteec_009149_1750",
  ortho_dataset_id: null,
  elevation_range_m: { min_m: -4520, max_m: -4180 },
  roughness_range_m: { min_m: 0.1, max_m: 4.5 },
};

describe("HiRISE Orthophoto & Terrain Overlay Selection", () => {
  it("1. enables and targets ortho_dataset_id when co-registered orthophoto is available", () => {
    assert.equal(isOrthoOverlayAvailable(manifestWithOrtho), true);
    assert.equal(resolveOverlayForManifest("ortho", manifestWithOrtho), "ortho");

    const url = buildTileTextureUrlStrict(baseTile, manifestWithOrtho, "ortho");
    assert.match(url, /\/terrain\/ortho\/hirise_psp_009149_1750_ortho\/texture\?/);
    assert.match(url, /overlay=ortho/);
  });

  it("2. marks orthophoto unavailable when ortho_dataset_id is null and never silently substitutes elevation", () => {
    assert.equal(isOrthoOverlayAvailable(manifestWithoutOrtho), false);
    assert.equal(resolveOverlayForManifest("ortho", manifestWithoutOrtho), "elevation");

    assert.throws(
      () => buildTileTextureUrlStrict(baseTile, manifestWithoutOrtho, "ortho"),
      (err) => err instanceof OverlayUnavailableError
    );
  });

  it("3. keeps elevation, slope, and TRI (roughness) overlays independently functional and switchable", () => {
    const elevUrl = buildTileTextureUrlStrict(baseTile, manifestWithoutOrtho, "elevation");
    assert.match(elevUrl, /\/terrain\/ortho\/hirise_dteec_009149_1750\/texture\?/);
    assert.match(elevUrl, /overlay=elevation/);
    assert.match(elevUrl, /vmin=-4520/);
    assert.match(elevUrl, /vmax=-4180/);

    const slopeUrl = buildTileTextureUrlStrict(baseTile, manifestWithoutOrtho, "slope");
    assert.match(slopeUrl, /\/terrain\/ortho\/hirise_dteec_009149_1750\/texture\?/);
    assert.match(slopeUrl, /overlay=slope/);

    const triUrl = buildTileTextureUrlStrict(baseTile, manifestWithoutOrtho, "roughness");
    assert.match(triUrl, /\/terrain\/ortho\/hirise_dteec_009149_1750\/texture\?/);
    assert.match(triUrl, /overlay=roughness/);
    assert.match(triUrl, /vmin=0\.1/);
    assert.match(triUrl, /vmax=4\.5/);

    assert.notEqual(elevUrl, slopeUrl);
    assert.notEqual(slopeUrl, triUrl);
  });
});
