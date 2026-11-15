import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  buildCompactedTileMeshGeometryData,
  buildValidTileBoundarySegments,
  fetchHeightGridForCesium,
  isValidElevationSample,
  parseHeightGridForCesium,
  TerrainFetchError,
} from "../terrainNoData.ts";

function makeTileFixture(
  elevations_m,
  valid_mask,
  rows = 3,
  cols = 3
) {
  return {
    grid_rows: rows,
    grid_cols: cols,
    local_bounds_m: {
      min_east_m: 0,
      max_east_m: 200,
      min_north_m: 0,
      max_north_m: 200,
    },
    elevations_m,
    valid_mask,
    normals: null,
  };
}

describe("Terrain No-Data Contract & Integrity", () => {
  it("1. preserves valid elevation of exactly zero (0.0 with valid_mask=1)", () => {
    assert.equal(isValidElevationSample(0, 1), true);
    const tile = makeTileFixture([0, 0, 0, 0], [1, 1, 1, 1], 2, 2);
    const mesh = buildCompactedTileMeshGeometryData(tile);
    assert.ok(mesh !== null);
    assert.equal(mesh.triangleCount, 2);
    assert.equal(mesh.compactedVertexCount, 4);
    for (let i = 0; i < 4; i += 1) {
      assert.equal(mesh.positions[i * 3 + 1], 0);
    }

    const hg = parseHeightGridForCesium({
      available: true,
      grid_rows: 2,
      grid_cols: 2,
      elevations_m: [0, 0, 0, 0],
      valid_mask: [1, 1, 1, 1],
    });
    assert.deepEqual(Array.from(hg.buffer), [0, 0, 0, 0]);
  });

  it("2. rejects null elevation with invalid mask (valid_mask=0)", () => {
    assert.equal(isValidElevationSample(null, 0), false);
    assert.throws(
      () =>
        parseHeightGridForCesium({
          available: true,
          grid_rows: 2,
          grid_cols: 2,
          elevations_m: [10, null, 20, 30],
          valid_mask: [1, 0, 1, 1],
        }),
      (err) => err instanceof TerrainFetchError && err.kind === "partial_nodata"
    );
  });

  it("3. rejects invalid mask (valid_mask=0) even when elevation is non-null", () => {
    assert.equal(isValidElevationSample(123.4, 0), false);
    const tile = makeTileFixture([10, 999.9, 20, 30], [1, 0, 1, 1], 2, 2);
    // Only 3 valid vertices -> 1 valid triangle (a=0, sw=2, se=3? Wait: a=0, b=1(invalid), sw=2, se=3 -> no triangle!)
    const mesh = buildCompactedTileMeshGeometryData(tile);
    assert.equal(mesh, null);

    assert.throws(
      () =>
        parseHeightGridForCesium({
          available: true,
          grid_rows: 2,
          grid_cols: 2,
          elevations_m: [10, 999.9, 20, 30],
          valid_mask: [1, 0, 1, 1],
        }),
      (err) => err instanceof TerrainFetchError && err.kind === "partial_nodata"
    );
  });

  it("4. rejects valid mask (valid_mask=1) with null elevation", () => {
    assert.equal(isValidElevationSample(null, 1), false);
    assert.throws(
      () =>
        parseHeightGridForCesium({
          available: true,
          grid_rows: 2,
          grid_cols: 2,
          elevations_m: [10, null, 20, 30],
          valid_mask: [1, 1, 1, 1],
        }),
      (err) => err instanceof TerrainFetchError && err.kind === "partial_nodata"
    );
  });

  it("5. all-invalid tile produces null Three.js mesh and explicit Cesium failure", () => {
    const tile = makeTileFixture([null, null, null, null], [0, 0, 0, 0], 2, 2);
    assert.equal(buildCompactedTileMeshGeometryData(tile), null);

    assert.throws(
      () =>
        parseHeightGridForCesium({
          available: false,
          grid_rows: 0,
          grid_cols: 0,
          elevations_m: [],
          valid_mask: [],
        }),
      (err) => err instanceof TerrainFetchError && err.kind === "unavailable"
    );
  });

  it("6, 11 & 12. mixed valid/invalid terrain omits triangles touching nodata and never substitutes refElev or 0", () => {
    // 3x3 grid where center-right vertex (r=1,c=2 -> idx=5) is invalid (null, mask=0)
    // and bottom-right vertex (r=2,c=2 -> idx=8) is invalid.
    // Elevations are all around -4500..-4480 (no 0, no refElev substitution).
    const elevs = [
      -4500, -4498, -4496,
      -4495, -4493, null,
      -4490, -4488, null,
    ];
    const mask = [
      1, 1, 1,
      1, 1, 0,
      1, 1, 0,
    ];
    const tile = makeTileFixture(elevs, mask, 3, 3);
    const mesh = buildCompactedTileMeshGeometryData(tile);
    assert.ok(mesh !== null);
    // Cells: (0,0)->2 tris, (0,1)->top-left tri(1,4,2) only (b=2 valid, sw=4 valid, a=1 valid; tri2 uses se=5 invalid),
    // (1,0)->2 tris, (1,1)->0 tris. Total = 5 triangles!
    assert.equal(mesh.triangleCount, 5);
    assert.equal(mesh.compactedVertexCount, 7);

    // Every compacted vertex elevation must be one of the real measured elevations, never 0 or -4500 fallback
    for (let i = 0; i < mesh.compactedVertexCount; i += 1) {
      const y = mesh.positions[i * 3 + 1];
      assert.ok(Number.isFinite(y));
      assert.ok(y <= -4488 && y >= -4500);
    }

    // Boundary segments must skip edges touching invalid vertices (idx 5 and idx 8)
    const segs = buildValidTileBoundarySegments(tile, 0, 200, 0, 200, -4494, 1);
    // Valid perimeter edges: (0,0)-(0,1), (0,1)-(0,2), (2,1)-(2,0), (2,0)-(1,0), (1,0)-(0,0) = 5 segments
    assert.equal(segs.length, 5 * 6);
  });

  it("7, 8, 9 & 10. Cesium fetch distinguishes HTTP error, malformed response, network failure, and abort while always settling counter", async () => {
    let settledCount = 0;
    const onSettled = () => {
      settledCount += 1;
    };

    // 7. HTTP error
    await assert.rejects(
      () =>
        fetchHeightGridForCesium("https://example.invalid/hg", {
          fetchImpl: async () => new Response("Not Found", { status: 404, statusText: "Not Found" }),
          onSettled,
        }),
      (err) => err instanceof TerrainFetchError && err.kind === "http_error" && err.status === 404
    );
    assert.equal(settledCount, 1);

    // 8. Malformed JSON / malformed schema
    await assert.rejects(
      () =>
        fetchHeightGridForCesium("https://example.invalid/hg", {
          fetchImpl: async () => new Response("{bad json", { status: 200 }),
          onSettled,
        }),
      (err) => err instanceof TerrainFetchError && err.kind === "malformed_response"
    );
    assert.equal(settledCount, 2);

    // 9. Network failure
    await assert.rejects(
      () =>
        fetchHeightGridForCesium("https://example.invalid/hg", {
          fetchImpl: async () => {
            throw new TypeError("Failed to fetch");
          },
          onSettled,
        }),
      (err) => err instanceof TerrainFetchError && err.kind === "network_error"
    );
    assert.equal(settledCount, 3);

    // 10. Aborted request
    const ac = new AbortController();
    ac.abort();
    await assert.rejects(
      () =>
        fetchHeightGridForCesium("https://example.invalid/hg", {
          signal: ac.signal,
          fetchImpl: async () => {
            throw new DOMException("The operation was aborted.", "AbortError");
          },
          onSettled,
        }),
      (err) => err instanceof TerrainFetchError && err.kind === "aborted"
    );
    assert.equal(settledCount, 4);
  });
});
