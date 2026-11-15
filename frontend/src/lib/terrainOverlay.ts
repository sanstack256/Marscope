import type { TerrainMeshManifest, TerrainMeshTile, TextureOverlayMode } from "@/types";

export class OverlayUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "OverlayUnavailableError";
  }
}

export function isOrthoOverlayAvailable(
  manifest: Pick<TerrainMeshManifest, "ortho_dataset_id"> | null | undefined
): boolean {
  return Boolean(manifest?.ortho_dataset_id && manifest.ortho_dataset_id.trim().length > 0);
}

/**
 * When a manifest loads with no paired co-registered orthophoto, do not leave
 * activeOverlayMode on "ortho" (which previously caused silent elevation substitution).
 */
export function resolveOverlayForManifest(
  currentOverlay: TextureOverlayMode,
  manifest: Pick<TerrainMeshManifest, "ortho_dataset_id"> | null | undefined
): TextureOverlayMode {
  if (currentOverlay === "ortho" && !isOrthoOverlayAvailable(manifest)) {
    return "elevation";
  }
  return currentOverlay;
}

/**
 * Build a tile texture URL strictly for the requested overlayMode.
 * Never substitutes "elevation" when "ortho" is unavailable.
 */
export function buildTileTextureUrlStrict(
  tile: Pick<TerrainMeshTile, "bounds">,
  manifest: Pick<
    TerrainMeshManifest,
    "dataset_id" | "ortho_dataset_id" | "elevation_range_m" | "roughness_range_m"
  >,
  overlayMode: TextureOverlayMode,
  options: { apiBaseUrl?: string; texSize?: number; maxSlopeDeg?: number } = {}
): string {
  const apiBaseUrl = options.apiBaseUrl ?? "/api";
  const texSize = options.texSize ?? 512;
  const maxSlopeDeg = options.maxSlopeDeg ?? 20;

  if (overlayMode === "ortho" && !isOrthoOverlayAvailable(manifest)) {
    throw new OverlayUnavailableError(
      `No paired, co-registered orthophoto is available for DEM '${manifest.dataset_id}'.`
    );
  }

  const texDatasetId =
    overlayMode === "ortho" && manifest.ortho_dataset_id
      ? manifest.ortho_dataset_id
      : manifest.dataset_id;

  const qs = new URLSearchParams({
    overlay: overlayMode,
    min_lat: tile.bounds.min_lat.toFixed(7),
    max_lat: tile.bounds.max_lat.toFixed(7),
    min_lon: tile.bounds.min_lon.toFixed(7),
    max_lon: tile.bounds.max_lon.toFixed(7),
    size: String(texSize),
  });
  if (overlayMode === "elevation" && manifest.elevation_range_m) {
    qs.set("vmin", String(manifest.elevation_range_m.min_m));
    qs.set("vmax", String(manifest.elevation_range_m.max_m));
  } else if (overlayMode === "roughness" && manifest.roughness_range_m) {
    qs.set("vmin", String(manifest.roughness_range_m.min_m));
    qs.set("vmax", String(manifest.roughness_range_m.max_m));
  } else if (overlayMode === "traversability_state") {
    qs.set("max_slope_deg", String(maxSlopeDeg));
  }
  return `${apiBaseUrl}/terrain/ortho/${encodeURIComponent(texDatasetId)}/texture?${qs.toString()}`;
}
