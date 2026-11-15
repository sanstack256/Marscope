/**
 * Scientific terrain no-data validation and geometry helpers for Three.js and Cesium.
 * Never fabricates, interpolates, or substitutes 0 or refElev for unavailable samples.
 */

export interface TileGridInput {
  grid_rows: number;
  grid_cols: number;
  local_bounds_m: {
    min_east_m: number;
    max_east_m: number;
    min_north_m: number;
    max_north_m: number;
  };
  elevations_m: Array<number | null>;
  valid_mask: number[];
  normals?: number[] | null;
}

export interface CompactedTileMeshData {
  positions: Float32Array;
  uvs: Float32Array;
  normals: Float32Array | null;
  indices: number[];
  triangleCount: number;
  compactedVertexCount: number;
}

export interface HeightGridPayload {
  dataset_id?: string;
  product_id?: string;
  available: boolean;
  grid_rows: number;
  grid_cols: number;
  valid_fraction?: number;
  elevations_m: Array<number | null>;
  valid_mask?: number[];
  sample_spacing_m?: { dx_m: number; dy_m: number } | null;
  native_resolution_m?: number | null;
}

export type TerrainFetchErrorKind =
  | "http_error"
  | "malformed_response"
  | "network_error"
  | "aborted"
  | "unavailable"
  | "partial_nodata";

export class TerrainFetchError extends Error {
  readonly kind: TerrainFetchErrorKind;
  readonly status?: number;

  constructor(kind: TerrainFetchErrorKind, message: string, status?: number) {
    super(message);
    this.name = "TerrainFetchError";
    this.kind = kind;
    this.status = status;
  }
}

/**
 * A sample is valid iff valid_mask is 1 AND elevation is a finite number (0 is valid).
 */
export function isValidElevationSample(
  elevation: number | null | undefined,
  validMaskValue: number | undefined
): elevation is number {
  return (
    validMaskValue === 1 &&
    elevation !== null &&
    elevation !== undefined &&
    typeof elevation === "number" &&
    Number.isFinite(elevation)
  );
}

/**
 * Build compacted Three.js BufferGeometry arrays containing ONLY valid measured vertices
 * referenced by valid triangles. Invalid vertices never enter the position buffer and
 * are never substituted with refElev or 0.
 */
export function buildCompactedTileMeshGeometryData(
  tile: TileGridInput,
  texSize = 512
): CompactedTileMeshData | null {
  const rows = tile.grid_rows;
  const cols = tile.grid_cols;
  if (rows < 2 || cols < 2) return null;
  const numVerts = rows * cols;
  if (tile.elevations_m.length !== numVerts || tile.valid_mask.length !== numVerts) {
    return null;
  }

  const validFlags = new Uint8Array(numVerts);
  for (let i = 0; i < numVerts; i += 1) {
    if (isValidElevationSample(tile.elevations_m[i], tile.valid_mask[i])) {
      validFlags[i] = 1;
    }
  }

  const rawTriangles: number[] = [];
  for (let r = 0; r < rows - 1; r += 1) {
    for (let c = 0; c < cols - 1; c += 1) {
      const a = r * cols + c;
      const b = a + 1;
      const sw = (r + 1) * cols + c;
      const se = sw + 1;

      if (validFlags[a] === 1 && validFlags[sw] === 1 && validFlags[b] === 1) {
        rawTriangles.push(a, sw, b);
      }
      if (validFlags[b] === 1 && validFlags[sw] === 1 && validFlags[se] === 1) {
        rawTriangles.push(b, sw, se);
      }
    }
  }

  if (rawTriangles.length === 0) return null;

  const vertexRemap = new Int32Array(numVerts).fill(-1);
  let compactCount = 0;
  for (let i = 0; i < rawTriangles.length; i += 1) {
    const gIdx = rawTriangles[i];
    if (vertexRemap[gIdx] === -1) {
      vertexRemap[gIdx] = compactCount;
      compactCount += 1;
    }
  }

  const positions = new Float32Array(compactCount * 3);
  const uvs = new Float32Array(compactCount * 2);
  const hasNormals = Array.isArray(tile.normals) && tile.normals.length === numVerts * 3;
  const normals = hasNormals ? new Float32Array(compactCount * 3) : null;

  const { min_east_m: minE, max_east_m: maxE, min_north_m: minN, max_north_m: maxN } =
    tile.local_bounds_m;

  for (let r = 0; r < rows; r += 1) {
    const vFrac = rows > 1 ? r / (rows - 1) : 0;
    const northM = maxN - vFrac * (maxN - minN);
    const zCoord = -northM;

    for (let c = 0; c < cols; c += 1) {
      const gIdx = r * cols + c;
      const cIdx = vertexRemap[gIdx];
      if (cIdx === -1) continue;

      const uFrac = cols > 1 ? c / (cols - 1) : 0;
      const eastM = minE + uFrac * (maxE - minE);
      const elev = tile.elevations_m[gIdx] as number;

      positions[cIdx * 3] = eastM;
      positions[cIdx * 3 + 1] = elev;
      positions[cIdx * 3 + 2] = zCoord;

      uvs[cIdx * 2] = (0.5 + uFrac * (texSize - 1)) / texSize;
      uvs[cIdx * 2 + 1] = 1 - (0.5 + vFrac * (texSize - 1)) / texSize;

      if (normals && tile.normals) {
        normals[cIdx * 3] = tile.normals[gIdx * 3];
        normals[cIdx * 3 + 1] = tile.normals[gIdx * 3 + 1];
        normals[cIdx * 3 + 2] = tile.normals[gIdx * 3 + 2];
      }
    }
  }

  const indices = new Array<number>(rawTriangles.length);
  for (let i = 0; i < rawTriangles.length; i += 1) {
    indices[i] = vertexRemap[rawTriangles[i]];
  }

  return {
    positions,
    uvs,
    normals,
    indices,
    triangleCount: indices.length / 3,
    compactedVertexCount: compactCount,
  };
}

/**
 * Emit LineSegments positions (6 floats per segment) along tile perimeter edges ONLY
 * where both adjacent perimeter vertices have valid measured elevations.
 */
export function buildValidTileBoundarySegments(
  tile: TileGridInput,
  minEastM: number,
  maxEastM: number,
  minNorthM: number,
  maxNorthM: number,
  refElevM: number,
  verticalExaggeration: number
): Float32Array {
  const rows = tile.grid_rows;
  const cols = tile.grid_cols;
  if (rows < 2 || cols < 2) return new Float32Array(0);

  const perimeter: Array<[number, number]> = [];
  for (let c = 0; c < cols; c += 1) perimeter.push([0, c]);
  for (let r = 1; r < rows; r += 1) perimeter.push([r, cols - 1]);
  for (let c = cols - 2; c >= 0; c -= 1) perimeter.push([rows - 1, c]);
  for (let r = rows - 2; r >= 0; r -= 1) perimeter.push([r, 0]);

  const segCoords: number[] = [];
  const toPoint = (r: number, c: number): [number, number, number] | null => {
    const idx = r * cols + c;
    const raw = tile.elevations_m[idx];
    if (!isValidElevationSample(raw, tile.valid_mask[idx])) return null;
    const vFrac = rows > 1 ? r / (rows - 1) : 0;
    const uFrac = cols > 1 ? c / (cols - 1) : 0;
    const eastM = minEastM + uFrac * (maxEastM - minEastM);
    const northM = maxNorthM - vFrac * (maxNorthM - minNorthM);
    return [eastM, (raw - refElevM) * verticalExaggeration + 2.5, -northM];
  };

  for (let i = 0; i < perimeter.length - 1; i += 1) {
    const p1 = toPoint(perimeter[i][0], perimeter[i][1]);
    const p2 = toPoint(perimeter[i + 1][0], perimeter[i + 1][1]);
    if (p1 && p2) {
      segCoords.push(p1[0], p1[1], p1[2], p2[0], p2[1], p2[2]);
    }
  }
  return new Float32Array(segCoords);
}

/**
 * Validate a backend /api/terrain/mesh/heightgrid payload for Cesium HeightmapTerrainData.
 * Cesium HeightmapTerrainData has no per-vertex validity mask and throws DeveloperError on NaN,
 * so unavailable or partial-nodata heightgrids MUST fail explicitly rather than substituting 0.
 */
export function parseHeightGridForCesium(payload: unknown): {
  buffer: Float32Array;
  width: number;
  height: number;
} {
  if (!payload || typeof payload !== "object") {
    throw new TerrainFetchError("malformed_response", "Heightgrid response is not a JSON object.");
  }
  const p = payload as Partial<HeightGridPayload>;
  if (p.available === false) {
    throw new TerrainFetchError("unavailable", "No DEM coverage available for requested Cesium tile.");
  }
  if (
    typeof p.grid_rows !== "number" ||
    typeof p.grid_cols !== "number" ||
    !Number.isInteger(p.grid_rows) ||
    !Number.isInteger(p.grid_cols) ||
    p.grid_rows <= 0 ||
    p.grid_cols <= 0 ||
    !Array.isArray(p.elevations_m)
  ) {
    throw new TerrainFetchError(
      "malformed_response",
      "Heightgrid response missing valid grid_rows, grid_cols, or elevations_m."
    );
  }
  const expectedLen = p.grid_rows * p.grid_cols;
  if (p.elevations_m.length !== expectedLen) {
    throw new TerrainFetchError(
      "malformed_response",
      `Heightgrid elevations_m length (${p.elevations_m.length}) != ${expectedLen}.`
    );
  }

  const hasMask = Array.isArray(p.valid_mask) && p.valid_mask.length > 0;
  if (hasMask && p.valid_mask!.length !== expectedLen) {
    throw new TerrainFetchError(
      "malformed_response",
      `Heightgrid valid_mask length (${p.valid_mask!.length}) != ${expectedLen}.`
    );
  }

  const out = new Float32Array(expectedLen);
  for (let i = 0; i < expectedLen; i += 1) {
    const h = p.elevations_m[i];
    const maskVal = hasMask ? p.valid_mask![i] : 1;
    if (!isValidElevationSample(h, maskVal)) {
      throw new TerrainFetchError(
        "partial_nodata",
        `Heightgrid contains unavailable/nodata sample at index ${i}; refusing to substitute 0.`
      );
    }
    out[i] = h;
  }

  return { buffer: out, width: p.grid_cols, height: p.grid_rows };
}

export async function fetchHeightGridForCesium(
  url: string,
  options: {
    fetchImpl?: typeof fetch;
    signal?: AbortSignal;
    onSettled?: () => void;
  } = {}
): Promise<{ buffer: Float32Array; width: number; height: number }> {
  const fetchFn = options.fetchImpl ?? fetch;
  try {
    let res: Response;
    try {
      res = await fetchFn(url, { signal: options.signal });
    } catch (err) {
      if (
        (err instanceof DOMException && err.name === "AbortError") ||
        (err instanceof Error && err.name === "AbortError")
      ) {
        throw new TerrainFetchError("aborted", "Terrain heightgrid request aborted.");
      }
      throw new TerrainFetchError(
        "network_error",
        err instanceof Error ? err.message : "Network failure fetching terrain heightgrid."
      );
    }

    if (!res.ok) {
      throw new TerrainFetchError(
        "http_error",
        `Terrain heightgrid HTTP ${res.status} ${res.statusText || ""}`.trim(),
        res.status
      );
    }

    let jsonBody: unknown;
    try {
      jsonBody = await res.json();
    } catch (err) {
      throw new TerrainFetchError(
        "malformed_response",
        err instanceof Error ? err.message : "Malformed JSON in terrain heightgrid response."
      );
    }

    return parseHeightGridForCesium(jsonBody);
  } finally {
    options.onSettled?.();
  }
}
