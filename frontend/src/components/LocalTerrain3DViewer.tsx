"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  Compass,
  Crosshair,
  Eye,
  Flag,
  Layers,
  Loader2,
  MapPin,
  Mountain,
  RefreshCw,
  Route as RouteIcon,
  Target,
} from "lucide-react";
import { API_BASE_URL } from "@/lib/constants";
import { useRoutingStore, type CameraPresetType } from "@/stores/useRoutingStore";
import type {
  PickedSurfacePoint,
  ScienceTarget,
  SurfacePickMode,
  TerrainMeshTile,
  TextureOverlayMode,
} from "@/types";

const MARS_EQUATORIAL_RADIUS_M = 3396190.0;

function latLonToLocalMeters(
  lat: number,
  lonEast: number,
  originLat: number,
  originLonEast: number
): { eastM: number; northM: number } {
  const mPerDegLat = (MARS_EQUATORIAL_RADIUS_M * Math.PI) / 180.0;
  const mPerDegLon =
    MARS_EQUATORIAL_RADIUS_M * Math.cos((originLat * Math.PI) / 180.0) * (Math.PI / 180.0);
  return {
    eastM: (lonEast - originLonEast) * mPerDegLon,
    northM: (lat - originLat) * mPerDegLat,
  };
}

interface TileMeshUserData {
  tile: TerrainMeshTile;
  minEastM: number;
  maxEastM: number;
  minNorthM: number;
  maxNorthM: number;
}

interface LocalTerrain3DViewerProps {
  targets?: ScienceTarget[];
  simulationProgressM?: number | null;
  onSurfaceInspect?: (point: PickedSurfacePoint) => void;
  compact?: boolean;
}

export function LocalTerrain3DViewer({
  targets = [],
  simulationProgressM = null,
  onSurfaceInspect,
  compact = false,
}: LocalTerrain3DViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const hoverHudRef = useRef<HTMLDivElement | null>(null);

  // Three.js scene object refs (never put inside React state to prevent 60fps re-renders)
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const terrainGroupRef = useRef<THREE.Group | null>(null);
  const overlayGroupRef = useRef<THREE.Group | null>(null);
  const refElevMRef = useRef<number>(-4500);
  const sceneInitializedRef = useRef<boolean>(false);
  const cameraAnimRef = useRef<{
    active: boolean;
    startPos: THREE.Vector3;
    endPos: THREE.Vector3;
    startTarget: THREE.Vector3;
    endTarget: THREE.Vector3;
    startTime: number;
    durationMs: number;
  } | null>(null);
  const tileCacheRef = useRef<Map<string, TerrainMeshTile>>(new Map());
  const textureCacheRef = useRef<Map<string, THREE.Texture>>(new Map());

  const [tilesLoading, setTilesLoading] = useState(false);
  const [tilesLoadedCount, setTilesLoadedCount] = useState(0);
  const [tileError, setTileError] = useState<string | null>(null);
  const [showTargets, setShowTargets] = useState(true);
  const [renderedVertexTotal, setRenderedVertexTotal] = useState(0);

  const selectedDemDatasetId = useRoutingStore((s) => s.selectedDemDatasetId);
  const meshManifest = useRoutingStore((s) => s.meshManifest);
  const manifestLoading = useRoutingStore((s) => s.manifestLoading);
  const manifestError = useRoutingStore((s) => s.manifestError);
  const activeLod = useRoutingStore((s) => s.activeLod);
  const activeOverlayMode = useRoutingStore((s) => s.activeOverlayMode);
  const verticalExaggeration = useRoutingStore((s) => s.verticalExaggeration);
  const surfacePickMode = useRoutingStore((s) => s.surfacePickMode);
  const startPoint = useRoutingStore((s) => s.startPoint);
  const destinationPoint = useRoutingStore((s) => s.destinationPoint);
  const customWaypoints = useRoutingStore((s) => s.customWaypoints);
  const selectedTargetIds = useRoutingStore((s) => s.selectedTargetIds);
  const activeRoute = useRoutingStore((s) => s.activeRoute);
  const selectedWaypointSeq = useRoutingStore((s) => s.selectedWaypointSeq);
  const cameraFocusRequest = useRoutingStore((s) => s.cameraFocusRequest);
  const cameraPresetRequest = useRoutingStore((s) => s.cameraPresetRequest);

  const fetchMeshManifest = useRoutingStore((s) => s.fetchMeshManifest);
  const setSelectedDemDatasetId = useRoutingStore((s) => s.setSelectedDemDatasetId);
  const setActiveLod = useRoutingStore((s) => s.setActiveLod);
  const setActiveOverlayMode = useRoutingStore((s) => s.setActiveOverlayMode);
  const setVerticalExaggeration = useRoutingStore((s) => s.setVerticalExaggeration);
  const setSurfacePickMode = useRoutingStore((s) => s.setSurfacePickMode);
  const requestCameraPreset = useRoutingStore((s) => s.requestCameraPreset);

  // Load initial DEM manifest on mount if absent (guard against retrying endlessly on error)
  useEffect(() => {
    if (!meshManifest && !manifestLoading && !manifestError) {
      void fetchMeshManifest(selectedDemDatasetId);
    }
  }, [meshManifest, manifestLoading, manifestError, selectedDemDatasetId, fetchMeshManifest]);

  const lodDescriptors = useMemo(() => {
    if (!meshManifest) return [];
    return meshManifest.tiles.filter((t) => t.lod === activeLod);
  }, [meshManifest, activeLod]);

  const sampleTileAtHit = useCallback(
    (intersect: THREE.Intersection): PickedSurfacePoint | null => {
      const meshObj = intersect.object as THREE.Mesh;
      const ud = meshObj.userData as TileMeshUserData | undefined;
      if (!ud?.tile) return null;

      const tile = ud.tile;
      const eastM = intersect.point.x;
      const northM = -intersect.point.z;

      const cols = Math.max(1, tile.grid_cols - 1);
      const rows = Math.max(1, tile.grid_rows - 1);
      const fracC = Math.min(
        1,
        Math.max(0, (eastM - ud.minEastM) / Math.max(1e-6, ud.maxEastM - ud.minEastM))
      );
      const fracN = Math.min(
        1,
        Math.max(0, (northM - ud.minNorthM) / Math.max(1e-6, ud.maxNorthM - ud.minNorthM))
      );

      const col = Math.min(tile.grid_cols - 1, Math.max(0, Math.round(fracC * cols)));
      const row = Math.min(tile.grid_rows - 1, Math.max(0, Math.round((1 - fracN) * rows)));
      const idx = row * tile.grid_cols + col;
      if (tile.valid_mask[idx] !== 1) return null;

      const elev = tile.elevations_m[idx];
      if (elev == null || !Number.isFinite(elev)) return null;

      const lat =
        tile.bounds.min_lat +
        fracN * (tile.bounds.max_lat - tile.bounds.min_lat);
      const lonEast =
        tile.bounds.min_lon +
        fracC * (tile.bounds.max_lon - tile.bounds.min_lon);

      return {
        lat: Number(lat.toFixed(6)),
        lon_east: Number(lonEast.toFixed(6)),
        elevation_m: Number(elev.toFixed(2)),
        slope_deg: tile.slope_deg?.[idx] ?? null,
        roughness_tri_m: tile.roughness_tri_m?.[idx] ?? null,
        dataset_id: tile.dataset_id,
      };
    },
    []
  );

  // Initialize Three.js WebGLRenderer, Scene, Camera, OrbitControls cleanly once
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const width = Math.max(320, container.clientWidth);
    const height = Math.max(240, container.clientHeight);

    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(width, height);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.08;
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#07090f");
    scene.fog = new THREE.FogExp2("#07090f", 0.000045);

    const camera = new THREE.PerspectiveCamera(45, width / height, 2, 120000);
    camera.position.set(0, 1450, 1850);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.075;
    controls.screenSpacePanning = false;
    controls.maxPolarAngle = Math.PI * 0.485;
    controls.minDistance = 40;
    controls.maxDistance = 45000;
    controls.target.set(0, 0, 0);

    controls.addEventListener("start", () => {
      cameraAnimRef.current = null;
    });

    // Physically inspired Martian directional lighting + soft dust bounce ambient
    const ambient = new THREE.AmbientLight("#6e5347", 0.72);
    const hemi = new THREE.HemisphereLight("#ffdfc4", "#231a16", 0.55);
    const sun = new THREE.DirectionalLight("#fff1df", 1.85);
    sun.position.set(2200, 3200, 1400);
    const fill = new THREE.DirectionalLight("#7aa2cc", 0.35);
    fill.position.set(-1800, 1200, -1600);
    scene.add(ambient, hemi, sun, fill);

    const terrainGroup = new THREE.Group();
    const overlayGroup = new THREE.Group();
    scene.add(terrainGroup);
    scene.add(overlayGroup);

    rendererRef.current = renderer;
    sceneRef.current = scene;
    cameraRef.current = camera;
    controlsRef.current = controls;
    terrainGroupRef.current = terrainGroup;
    overlayGroupRef.current = overlayGroup;
    sceneInitializedRef.current = true;

    const raycaster = new THREE.Raycaster();
    const pointerNdc = new THREE.Vector2();
    let pointerDownPos = { x: 0, y: 0 };

    const handlePointerDown = (e: PointerEvent) => {
      pointerDownPos = { x: e.clientX, y: e.clientY };
    };

    const handlePointerMove = (e: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;
      pointerNdc.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointerNdc.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointerNdc, camera);
      const hits = raycaster.intersectObjects(terrainGroup.children, false);
      const hud = hoverHudRef.current;
      if (!hud) return;
      if (hits.length > 0) {
        const pt = sampleTileAtHit(hits[0]);
        if (pt) {
          const slopeText = pt.slope_deg != null ? `${pt.slope_deg.toFixed(1)}°` : "N/A";
          const triText = pt.roughness_tri_m != null ? `${pt.roughness_tri_m.toFixed(2)}m` : "N/A";
          hud.textContent = `${pt.lat.toFixed(5)}°, ${pt.lon_east.toFixed(5)}° E  |  Elev: ${pt.elevation_m.toFixed(1)} m  |  Slope: ${slopeText}  |  TRI: ${triText}`;
          return;
        }
      }
      hud.textContent = "Hover valid DEM surface for telemetry · Drag to orbit · Right-drag to pan · Wheel to zoom";
    };

    const handlePointerUp = (e: PointerEvent) => {
      const moved = Math.hypot(e.clientX - pointerDownPos.x, e.clientY - pointerDownPos.y);
      if (moved > 5) return; // Dragging camera, not clicking
      const rect = renderer.domElement.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;
      pointerNdc.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointerNdc.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointerNdc, camera);

      // Check interactive 3D overlay markers first (science targets, route stops)
      const markerHits = raycaster.intersectObjects(overlayGroup.children, true);
      for (const hit of markerHits) {
        const meta = hit.object.userData as { kind?: string; targetId?: string; waypointSeq?: number } | undefined;
        if (meta?.kind === "science_target" && meta.targetId) {
          useRoutingStore.getState().toggleTargetId(meta.targetId);
          return;
        }
        if (meta?.kind === "route_waypoint" && meta.waypointSeq != null) {
          useRoutingStore.getState().selectWaypoint(meta.waypointSeq, false);
          return;
        }
      }

      // Otherwise intersect DEM surface
      const hits = raycaster.intersectObjects(terrainGroup.children, false);
      if (hits.length === 0) return;
      const picked = sampleTileAtHit(hits[0]);
      if (!picked) return;

      const st = useRoutingStore.getState();
      st.setPickedSurfacePoint(picked);
      if (onSurfaceInspect) onSurfaceInspect(picked);

      if (st.surfacePickMode === "set_start") {
        st.setStartPoint({
          lat: picked.lat,
          lon_east: picked.lon_east,
          label: `Start (${picked.lat.toFixed(4)}°, ${picked.lon_east.toFixed(4)}°)`,
        });
        st.setSurfacePickMode("inspect");
      } else if (st.surfacePickMode === "set_destination") {
        st.setDestinationPoint({
          lat: picked.lat,
          lon_east: picked.lon_east,
          label: `Dest (${picked.lat.toFixed(4)}°, ${picked.lon_east.toFixed(4)}°)`,
        });
        st.setSurfacePickMode("inspect");
      } else if (st.surfacePickMode === "add_waypoint") {
        st.addCustomWaypoint({
          lat: picked.lat,
          lon_east: picked.lon_east,
          label: `Waypt #${st.customWaypoints.length + 1}`,
        });
      }
    };

    renderer.domElement.addEventListener("pointerdown", handlePointerDown);
    renderer.domElement.addEventListener("pointermove", handlePointerMove);
    renderer.domElement.addEventListener("pointerup", handlePointerUp);

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = Math.max(200, Math.floor(entry.contentRect.width));
        const h = Math.max(200, Math.floor(entry.contentRect.height));
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
      }
    });
    resizeObserver.observe(container);

    let rafId = 0;
    const animate = () => {
      rafId = window.requestAnimationFrame(animate);
      const anim = cameraAnimRef.current;
      if (anim?.active) {
        const elapsed = performance.now() - anim.startTime;
        const t = Math.min(1, elapsed / Math.max(1, anim.durationMs));
        const ease = 1 - Math.pow(1 - t, 3);
        camera.position.lerpVectors(anim.startPos, anim.endPos, ease);
        controls.target.lerpVectors(anim.startTarget, anim.endTarget, ease);
        if (t >= 1) anim.active = false;
      }
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      window.cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointerdown", handlePointerDown);
      renderer.domElement.removeEventListener("pointermove", handlePointerMove);
      renderer.domElement.removeEventListener("pointerup", handlePointerUp);
      controls.dispose();
      renderer.dispose();
      sceneInitializedRef.current = false;
      rendererRef.current = null;
      sceneRef.current = null;
      cameraRef.current = null;
      controlsRef.current = null;
      terrainGroupRef.current = null;
      overlayGroupRef.current = null;
    };
  }, [onSurfaceInspect, sampleTileAtHit]);

  // Helper to apply smooth camera transition
  const animateCameraTo = useCallback(
    (endPos: THREE.Vector3, endTarget: THREE.Vector3, durationMs = 550) => {
      const camera = cameraRef.current;
      const controls = controlsRef.current;
      if (!camera || !controls) return;
      cameraAnimRef.current = {
        active: true,
        startPos: camera.position.clone(),
        endPos,
        startTarget: controls.target.clone(),
        endTarget,
        startTime: performance.now(),
        durationMs,
      };
    },
    []
  );

  // Load DEM mesh tiles + synced overlay textures whenever manifest, LOD, or overlay changes
  useEffect(() => {
    const terrainGroup = terrainGroupRef.current;
    if (!meshManifest || !terrainGroup || lodDescriptors.length === 0) return;

    const controller = new AbortController();
    let cancelled = false;
    setTilesLoading(true);
    setTileError(null);

    const texDatasetId =
      activeOverlayMode === "ortho" && meshManifest.ortho_dataset_id
        ? meshManifest.ortho_dataset_id
        : meshManifest.dataset_id;
    const texOverlay: TextureOverlayMode =
      activeOverlayMode === "ortho" && !meshManifest.ortho_dataset_id
        ? "elevation"
        : activeOverlayMode;

    const clearGroupChildren = (group: THREE.Group) => {
      while (group.children.length > 0) {
        const obj = group.children[group.children.length - 1] as THREE.Mesh;
        group.remove(obj);
        if (obj.geometry) obj.geometry.dispose();
        const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
        mats.forEach((m) => m?.dispose());
      }
    };

    const loadAllTiles = async () => {
      try {
        const fetchedTiles: TerrainMeshTile[] = await Promise.all(
          lodDescriptors.map(async (desc) => {
            const cacheKey = `${meshManifest.dataset_id}:${desc.tile_id}`;
            const cached = tileCacheRef.current.get(cacheKey);
            if (cached) return cached;

            const qs = new URLSearchParams({
              dataset_id: meshManifest.dataset_id,
              origin_lat: String(meshManifest.origin.lat),
              origin_lon_east: String(meshManifest.origin.lon_east),
              grid_size: String(desc.grid_cols),
            });
            const res = await fetch(
              `${API_BASE_URL}/terrain/mesh/tiles/${encodeURIComponent(desc.tile_id)}?${qs.toString()}`,
              { signal: controller.signal }
            );
            if (!res.ok) {
              const errBody = await res.json().catch(() => ({}));
              throw new Error(errBody?.detail || `HTTP ${res.status} fetching tile ${desc.tile_id}`);
            }
            const data: TerrainMeshTile = await res.json();
            tileCacheRef.current.set(cacheKey, data);
            if (tileCacheRef.current.size > 48) {
              const firstKey = tileCacheRef.current.keys().next().value;
              if (firstKey) tileCacheRef.current.delete(firstKey);
            }
            return data;
          })
        );

        if (cancelled || !terrainGroupRef.current) return;

        // Establish a stable local elevation baseline (mean elev across loaded tiles)
        let elevSum = 0;
        let elevCount = 0;
        fetchedTiles.forEach((t) => {
          if (t.elevation_min_m != null && t.elevation_max_m != null) {
            elevSum += 0.5 * (t.elevation_min_m + t.elevation_max_m);
            elevCount += 1;
          }
        });
        if (elevCount > 0) {
          refElevMRef.current = elevSum / elevCount;
        }

        clearGroupChildren(terrainGroupRef.current);

        let totalVerts = 0;
        const texLoader = new THREE.TextureLoader();

        fetchedTiles.forEach((tile) => {
          const rows = tile.grid_rows;
          const cols = tile.grid_cols;
          const numVerts = rows * cols;
          const positions = new Float32Array(numVerts * 3);
          const uvs = new Float32Array(numVerts * 2);

          const minE = tile.local_bounds_m.min_east_m;
          const maxE = tile.local_bounds_m.max_east_m;
          const minN = tile.local_bounds_m.min_north_m;
          const maxN = tile.local_bounds_m.max_north_m;

          for (let r = 0; r < rows; r += 1) {
            const vFrac = rows > 1 ? r / (rows - 1) : 0; // 0=North, 1=South
            const northM = maxN - vFrac * (maxN - minN);
            const zCoord = -northM;

            for (let c = 0; c < cols; c += 1) {
              const uFrac = cols > 1 ? c / (cols - 1) : 0; // 0=West, 1=East
              const eastM = minE + uFrac * (maxE - minE);
              const idx = r * cols + c;
              const rawElev = tile.elevations_m[idx];
              const yCoord =
                tile.valid_mask[idx] === 1 && rawElev != null && Number.isFinite(rawElev)
                  ? rawElev
                  : refElevMRef.current;

              positions[idx * 3] = eastM;
              positions[idx * 3 + 1] = yCoord;
              positions[idx * 3 + 2] = zCoord;

              uvs[idx * 2] = uFrac;
              uvs[idx * 2 + 1] = 1 - vFrac; // Match PNG flipY=true (top = North = v=1)
            }
          }

          // Emit triangles ONLY when all 3 vertices have valid data (strict nodata omission)
          const indices: number[] = [];
          for (let r = 0; r < rows - 1; r += 1) {
            for (let c = 0; c < cols - 1; c += 1) {
              const a = r * cols + c;
              const b = a + 1;
              const sw = (r + 1) * cols + c;
              const se = sw + 1;

              const va = tile.valid_mask[a] === 1;
              const vb = tile.valid_mask[b] === 1;
              const vsw = tile.valid_mask[sw] === 1;
              const vse = tile.valid_mask[se] === 1;

              if (va && vsw && vb) {
                indices.push(a, sw, b);
              }
              if (vb && vsw && vse) {
                indices.push(b, sw, se);
              }
            }
          }

          if (indices.length === 0) return;
          totalVerts += tile.valid_vertex_count;

          const geom = new THREE.BufferGeometry();
          geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
          geom.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
          geom.setIndex(indices);
          geom.computeVertexNormals();
          geom.computeBoundingBox();
          geom.computeBoundingSphere();

          const mat = new THREE.MeshStandardMaterial({
            color: new THREE.Color("#9e7a66"),
            roughness: 0.9,
            metalness: 0.04,
            side: THREE.FrontSide,
          });

          const mesh = new THREE.Mesh(geom, mat);
          mesh.userData = {
            tile,
            minEastM: minE,
            maxEastM: maxE,
            minNorthM: minN,
            maxNorthM: maxN,
          } satisfies TileMeshUserData;

          const texQs = new URLSearchParams({
            overlay: texOverlay,
            min_lat: tile.bounds.min_lat.toFixed(7),
            max_lat: tile.bounds.max_lat.toFixed(7),
            min_lon: tile.bounds.min_lon.toFixed(7),
            max_lon: tile.bounds.max_lon.toFixed(7),
            size: activeLod >= 2 ? "512" : "512",
          });
          const texUrl = `${API_BASE_URL}/terrain/ortho/${encodeURIComponent(texDatasetId)}/texture?${texQs.toString()}`;
          const cachedTex = textureCacheRef.current.get(texUrl);
          if (cachedTex) {
            mat.color.set("#ffffff");
            mat.map = cachedTex;
            mat.needsUpdate = true;
          } else {
            texLoader.load(
              texUrl,
              (loadedTex) => {
                if (cancelled) {
                  loadedTex.dispose();
                  return;
                }
                loadedTex.colorSpace = THREE.SRGBColorSpace;
                loadedTex.wrapS = THREE.ClampToEdgeWrapping;
                loadedTex.wrapT = THREE.ClampToEdgeWrapping;
                loadedTex.anisotropy = Math.min(4, rendererRef.current?.capabilities.getMaxAnisotropy() || 1);
                textureCacheRef.current.set(texUrl, loadedTex);
                if (textureCacheRef.current.size > 48) {
                  const oldest = textureCacheRef.current.keys().next().value;
                  if (oldest) {
                    textureCacheRef.current.get(oldest)?.dispose();
                    textureCacheRef.current.delete(oldest);
                  }
                }
                mat.color.set("#ffffff");
                mat.map = loadedTex;
                mat.needsUpdate = true;
              },
              undefined,
              () => {
                // Keep terrain surface rendered with shaded base tone if texture fails
              }
            );
          }

          terrainGroupRef.current?.add(mesh);
        });

        const currentExag = useRoutingStore.getState().verticalExaggeration;
        terrainGroupRef.current.scale.set(1, currentExag, 1);
        terrainGroupRef.current.position.set(0, -refElevMRef.current * currentExag, 0);

        setTilesLoadedCount(fetchedTiles.length);
        setRenderedVertexTotal(totalVerts);
        setTilesLoading(false);

        // Fit camera automatically to new DEM footprint extent
        const wM = meshManifest.physical_extent_m.width_m || 2400;
        const hM = meshManifest.physical_extent_m.height_m || 2400;
        const span = Math.max(wM, hM, 600);
        const startPos = new THREE.Vector3(span * 0.42, span * 0.45, span * 0.56);
        const startTarget = new THREE.Vector3(0, 0, 0);
        if (cameraRef.current && controlsRef.current) {
          cameraRef.current.far = Math.max(80000, span * 25);
          cameraRef.current.updateProjectionMatrix();
          controlsRef.current.maxDistance = Math.max(12000, span * 8);
          animateCameraTo(startPos, startTarget, 450);
        }
      } catch (err: unknown) {
        if ((err as { name?: string })?.name === "AbortError" || cancelled) return;
        setTilesLoading(false);
        setTileError(err instanceof Error ? err.message : "Failed to load terrain mesh tiles.");
      }
    };

    void loadAllTiles();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [meshManifest, activeLod, activeOverlayMode, lodDescriptors, animateCameraTo]);

  // Apply O(1) vertical exaggeration & rebuild 3D routes/markers cleanly
  useEffect(() => {
    const terrainGroup = terrainGroupRef.current;
    const overlayGroup = overlayGroupRef.current;
    if (!terrainGroup || !overlayGroup || !meshManifest) return;

    const exag = verticalExaggeration;
    const refElev = refElevMRef.current;
    terrainGroup.scale.set(1, exag, 1);
    terrainGroup.position.set(0, -refElev * exag, 0);

    // Clear old overlay objects cleanly
    while (overlayGroup.children.length > 0) {
      const obj = overlayGroup.children[overlayGroup.children.length - 1];
      overlayGroup.remove(obj);
      obj.traverse((child) => {
        const meshChild = child as THREE.Mesh;
        if (meshChild.geometry) meshChild.geometry.dispose();
        if (meshChild.material) {
          const mats = Array.isArray(meshChild.material)
            ? meshChild.material
            : [meshChild.material];
          mats.forEach((m) => m?.dispose());
        }
      });
    }

    const originLat = meshManifest.origin.lat;
    const originLon = meshManifest.origin.lon_east;
    const span = Math.max(
      meshManifest.physical_extent_m.width_m || 2000,
      meshManifest.physical_extent_m.height_m || 2000,
      500
    );
    const pinScale = Math.max(6, Math.min(85, span * 0.008));

    const toSceneVec = (lat: number, lonEast: number, elevationM?: number | null, liftM = 4) => {
      const { eastM, northM } = latLonToLocalMeters(lat, lonEast, originLat, originLon);
      const yBase = elevationM != null && Number.isFinite(elevationM) ? elevationM : refElev;
      return new THREE.Vector3(eastM, (yBase - refElev) * exag + liftM, -northM);
    };

    // Approximate surface elevation from loaded tile cache for un-computed pins
    const lookupElevNear = (lat: number, lonEast: number): number | null => {
      for (const obj of terrainGroup.children) {
        const ud = obj.userData as TileMeshUserData | undefined;
        if (!ud?.tile) continue;
        const b = ud.tile.bounds;
        if (lat >= b.min_lat && lat <= b.max_lat && lonEast >= b.min_lon && lonEast <= b.max_lon) {
          const row = Math.round(
            ((b.max_lat - lat) / Math.max(1e-9, b.max_lat - b.min_lat)) *
              (ud.tile.grid_rows - 1)
          );
          const col = Math.round(
            ((lonEast - b.min_lon) / Math.max(1e-9, b.max_lon - b.min_lon)) *
              (ud.tile.grid_cols - 1)
          );
          const idx =
            Math.max(0, Math.min(ud.tile.grid_rows - 1, row)) * ud.tile.grid_cols +
            Math.max(0, Math.min(ud.tile.grid_cols - 1, col));
          const val = ud.tile.elevations_m[idx];
          if (ud.tile.valid_mask[idx] === 1 && val != null && Number.isFinite(val)) {
            return val;
          }
        }
      }
      return null;
    };

    const addBeaconPin = (
      pos: THREE.Vector3,
      colorHex: string,
      radiusScale = 1,
      userData: Record<string, unknown> = {}
    ) => {
      const poleHeight = pinScale * 2.2 * radiusScale;
      const stemGeom = new THREE.CylinderGeometry(
        pinScale * 0.14 * radiusScale,
        pinScale * 0.14 * radiusScale,
        poleHeight,
        8
      );
      const stemMat = new THREE.MeshBasicMaterial({ color: colorHex });
      const stem = new THREE.Mesh(stemGeom, stemMat);
      stem.position.set(pos.x, pos.y + poleHeight * 0.5, pos.z);
      stem.userData = userData;

      const headGeom = new THREE.SphereGeometry(pinScale * 0.52 * radiusScale, 14, 14);
      const headMat = new THREE.MeshBasicMaterial({ color: colorHex });
      const head = new THREE.Mesh(headGeom, headMat);
      head.position.set(pos.x, pos.y + poleHeight, pos.z);
      head.userData = userData;

      overlayGroup.add(stem, head);
    };

    // Render Science Targets inside DEM bounds
    if (showTargets && targets.length > 0) {
      const b = meshManifest.requested_bounds;
      targets.forEach((t) => {
        if (
          t.latitude < b.min_lat - 0.01 ||
          t.latitude > b.max_lat + 0.01 ||
          t.longitude < b.min_lon - 0.01 ||
          t.longitude > b.max_lon + 0.01
        ) {
          return;
        }
        const selected = selectedTargetIds.includes(t.id);
        const elev = t.elevation_m ?? lookupElevNear(t.latitude, t.longitude);
        const pos = toSceneVec(t.latitude, t.longitude, elev, 2);
        addBeaconPin(pos, selected ? "#fde047" : "#a855f7", selected ? 1.25 : 0.85, {
          kind: "science_target",
          targetId: t.id,
        });
      });
    }

    // Render custom waypoints
    customWaypoints.forEach((wp) => {
      const elev = lookupElevNear(wp.lat, wp.lon_east);
      const pos = toSceneVec(wp.lat, wp.lon_east, elev, 2);
      addBeaconPin(pos, "#f59e0b", 0.95);
    });

    // Render explicit Start & Destination markers
    if (startPoint) {
      const elev = activeRoute?.vertices[0]?.elevation_m ?? lookupElevNear(startPoint.lat, startPoint.lon_east);
      addBeaconPin(toSceneVec(startPoint.lat, startPoint.lon_east, elev, 2), "#10b981", 1.3);
    }
    if (destinationPoint) {
      const elev = lookupElevNear(destinationPoint.lat, destinationPoint.lon_east);
      addBeaconPin(toSceneVec(destinationPoint.lat, destinationPoint.lon_east, elev, 1.3), "#f43f5e", 1.3);
    }

    // Render Active Route 3D Tube + Return Leg + Direction Cones + Waypoint Highlights
    if (activeRoute && activeRoute.vertices.length >= 2) {
      const returnLegStartSeq =
        activeRoute.legs.find((l) => l.is_return_leg)?.vertex_start_seq ?? Number.POSITIVE_INFINITY;

      const buildTube = (pts: THREE.Vector3[], colorHex: string) => {
        if (pts.length < 2) return;
        const curve = new THREE.CatmullRomCurve3(pts, false, "catmullrom", 0.08);
        const segCount = Math.min(400, Math.max(32, pts.length * 4));
        const tubeGeom = new THREE.TubeGeometry(curve, segCount, pinScale * 0.24, 8, false);
        const tubeMat = new THREE.MeshStandardMaterial({
          color: colorHex,
          emissive: colorHex,
          emissiveIntensity: 0.45,
          roughness: 0.35,
        });
        overlayGroup.add(new THREE.Mesh(tubeGeom, tubeMat));
      };

      const outboundPts: THREE.Vector3[] = [];
      const returnPts: THREE.Vector3[] = [];
      activeRoute.vertices.forEach((v) => {
        const pt = toSceneVec(v.lat, v.lon_east, v.elevation_m, 3.5);
        if (v.seq <= returnLegStartSeq) outboundPts.push(pt);
        if (v.seq >= returnLegStartSeq) returnPts.push(pt);
      });

      buildTube(outboundPts, "#38bdf8");
      if (returnPts.length >= 2) {
        buildTube(returnPts, "#fb923c");
      }

      // 3D directional heading cones along instructions/segments
      const upVec = new THREE.Vector3(0, 1, 0);
      const stepStride = Math.max(1, Math.floor(activeRoute.vertices.length / 18));
      for (let i = 0; i < activeRoute.vertices.length - 1; i += stepStride) {
        const v0 = activeRoute.vertices[i];
        const v1 = activeRoute.vertices[i + 1];
        const p0 = toSceneVec(v0.lat, v0.lon_east, v0.elevation_m, 5.5);
        const p1 = toSceneVec(v1.lat, v1.lon_east, v1.elevation_m, 5.5);
        const dir = new THREE.Vector3().subVectors(p1, p0);
        if (dir.lengthSq() < 1) continue;
        dir.normalize();
        const isRet = v0.seq >= returnLegStartSeq;
        const coneGeom = new THREE.ConeGeometry(pinScale * 0.45, pinScale * 1.15, 10);
        const coneMat = new THREE.MeshBasicMaterial({
          color: isRet ? "#fdba74" : "#bae6fd",
        });
        const cone = new THREE.Mesh(coneGeom, coneMat);
        cone.position.copy(p0).lerp(p1, 0.5);
        cone.quaternion.setFromUnitVectors(upVec, dir);
        overlayGroup.add(cone);
      }

      // Clickable route stop spheres + selected waypoint halo ring
      activeRoute.vertices
        .filter((v) => v.is_stop || selectedWaypointSeq === v.seq)
        .forEach((v) => {
          const isSel = selectedWaypointSeq === v.seq;
          const pos = toSceneVec(v.lat, v.lon_east, v.elevation_m, 5.5);
          const orbGeom = new THREE.SphereGeometry(pinScale * (isSel ? 0.65 : 0.4), 14, 14);
          const orbMat = new THREE.MeshBasicMaterial({
            color: isSel ? "#fde047" : "#38bdf8",
          });
          const orb = new THREE.Mesh(orbGeom, orbMat);
          orb.position.copy(pos);
          orb.userData = { kind: "route_waypoint", waypointSeq: v.seq };
          overlayGroup.add(orb);

          if (isSel) {
            const ringGeom = new THREE.RingGeometry(pinScale * 0.9, pinScale * 1.35, 24);
            const ringMat = new THREE.MeshBasicMaterial({
              color: "#fde047",
              side: THREE.DoubleSide,
            });
            const ring = new THREE.Mesh(ringGeom, ringMat);
            ring.rotation.x = -Math.PI / 2;
            ring.position.set(pos.x, pos.y + 1, pos.z);
            overlayGroup.add(ring);
          }
        });

      // Moving EVA astronaut position beacon (synchronized with /simulation timeline scrubber)
      if (simulationProgressM != null && Number.isFinite(simulationProgressM)) {
        const verts = activeRoute.vertices;
        let astroPos = toSceneVec(verts[0].lat, verts[0].lon_east, verts[0].elevation_m, 8);
        for (let i = 0; i < verts.length - 1; i += 1) {
          const a = verts[i];
          const b = verts[i + 1];
          if (
            simulationProgressM >= a.cumulative_distance_m &&
            simulationProgressM <= b.cumulative_distance_m
          ) {
            const frac =
              (simulationProgressM - a.cumulative_distance_m) /
              Math.max(1e-6, b.cumulative_distance_m - a.cumulative_distance_m);
            const pa = toSceneVec(a.lat, a.lon_east, a.elevation_m, 8);
            const pb = toSceneVec(b.lat, b.lon_east, b.elevation_m, 8);
            astroPos = pa.lerp(pb, Math.min(1, Math.max(0, frac)));
            break;
          }
          if (i === verts.length - 2 && simulationProgressM >= b.cumulative_distance_m) {
            astroPos = toSceneVec(b.lat, b.lon_east, b.elevation_m, 8);
          }
        }
        const roverGeom = new THREE.OctahedronGeometry(pinScale * 0.85, 0);
        const roverMat = new THREE.MeshStandardMaterial({
          color: "#22d3ee",
          emissive: "#06b6d4",
          emissiveIntensity: 0.75,
        });
        const roverMesh = new THREE.Mesh(roverGeom, roverMat);
        roverMesh.position.copy(astroPos);
        overlayGroup.add(roverMesh);
      }
    }
  }, [
    meshManifest,
    verticalExaggeration,
    activeRoute,
    startPoint,
    destinationPoint,
    customWaypoints,
    targets,
    showTargets,
    selectedTargetIds,
    selectedWaypointSeq,
    simulationProgressM,
    tilesLoadedCount,
  ]);

  // Respond to external camera focus requests (e.g. clicking an instruction row or target)
  useEffect(() => {
    if (!cameraFocusRequest || !meshManifest) return;
    const { eastM, northM } = latLonToLocalMeters(
      cameraFocusRequest.lat,
      cameraFocusRequest.lon_east,
      meshManifest.origin.lat,
      meshManifest.origin.lon_east
    );
    const yBase =
      cameraFocusRequest.elevation_m != null
        ? (cameraFocusRequest.elevation_m - refElevMRef.current) * verticalExaggeration
        : 0;
    const span = Math.max(meshManifest.physical_extent_m.width_m || 1200, 400);
    const offset = Math.max(180, Math.min(600, span * 0.18));
    animateCameraTo(
      new THREE.Vector3(eastM + offset * 0.65, yBase + offset * 0.85, -northM + offset * 0.75),
      new THREE.Vector3(eastM, yBase, -northM),
      480
    );
  }, [cameraFocusRequest, meshManifest, verticalExaggeration, animateCameraTo]);

  // Respond to camera presets (`oblique`, `top_down`, `focus_route`, `reset`)
  useEffect(() => {
    if (!cameraPresetRequest || !meshManifest) return;
    const wM = meshManifest.physical_extent_m.width_m || 2000;
    const hM = meshManifest.physical_extent_m.height_m || 2000;
    const span = Math.max(wM, hM, 600);
    const preset: CameraPresetType = cameraPresetRequest.preset;

    if (preset === "top_down") {
      animateCameraTo(new THREE.Vector3(0, span * 1.15, 25), new THREE.Vector3(0, 0, 0), 500);
    } else if (preset === "oblique" || preset === "reset") {
      animateCameraTo(
        new THREE.Vector3(span * 0.42, span * 0.45, span * 0.56),
        new THREE.Vector3(0, 0, 0),
        500
      );
    } else if (preset === "focus_route" && activeRoute && activeRoute.vertices.length >= 2) {
      let minE = Infinity;
      let maxE = -Infinity;
      let minN = Infinity;
      let maxN = -Infinity;
      let elevSum = 0;
      activeRoute.vertices.forEach((v) => {
        const { eastM, northM } = latLonToLocalMeters(
          v.lat,
          v.lon_east,
          meshManifest.origin.lat,
          meshManifest.origin.lon_east
        );
        minE = Math.min(minE, eastM);
        maxE = Math.max(maxE, eastM);
        minN = Math.min(minN, northM);
        maxN = Math.max(maxN, northM);
        elevSum += v.elevation_m;
      });
      const cx = 0.5 * (minE + maxE);
      const cz = -0.5 * (minN + maxN);
      const cy =
        (elevSum / activeRoute.vertices.length - refElevMRef.current) * verticalExaggeration;
      const routeSpan = Math.max(maxE - minE, maxN - minN, 350);
      animateCameraTo(
        new THREE.Vector3(cx + routeSpan * 0.55, cy + routeSpan * 0.72, cz + routeSpan * 0.65),
        new THREE.Vector3(cx, cy, cz),
        520
      );
    }
  }, [cameraPresetRequest, meshManifest, activeRoute, verticalExaggeration, animateCameraTo]);

  const pickModes: Array<{ id: SurfacePickMode; label: string; icon: typeof Crosshair; activeClass: string }> = [
    { id: "inspect", label: "Inspect", icon: Crosshair, activeClass: "bg-slate-700 text-white" },
    { id: "set_start", label: "Set Start", icon: MapPin, activeClass: "bg-emerald-600 text-white" },
    { id: "add_waypoint", label: "+Waypt", icon: Flag, activeClass: "bg-amber-600 text-white" },
    { id: "set_destination", label: "Set Dest", icon: Target, activeClass: "bg-rose-600 text-white" },
  ];

  const overlays: Array<{ id: TextureOverlayMode; label: string }> = [
    { id: "ortho", label: "HiRISE Ortho" },
    { id: "elevation", label: "Elevation" },
    { id: "slope", label: "Slope (°)" },
    { id: "roughness", label: "TRI" },
  ];

  return (
    <div className="relative w-full h-full min-h-[380px] bg-[#07090f] rounded-xl overflow-hidden border border-[#1e2638] select-none">
      {/* Three.js WebGL Mount */}
      <div ref={containerRef} className="w-full h-full cursor-crosshair" />

      {/* Top-Left DEM, LOD & Texture Controls */}
      <div className="absolute top-2.5 left-2.5 z-10 flex flex-wrap items-center gap-1.5 max-w-[70%]">
        {meshManifest && meshManifest.available_dems.length > 0 && (
          <select
            value={selectedDemDatasetId}
            onChange={(e) => setSelectedDemDatasetId(e.target.value)}
            className="bg-[#0b101b]/95 border border-[#243047] rounded-lg px-2 py-1 text-[11px] font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
            title="Select verified local DEM product"
          >
            {meshManifest.available_dems.map((d) => (
              <option key={d.dataset_id} value={d.dataset_id}>
                {d.dataset_id} ({d.native_resolution_m ? `${d.native_resolution_m.toFixed(1)} m/px` : "DEM"})
              </option>
            ))}
          </select>
        )}

        {/* LOD Selector */}
        <div className="flex bg-[#0b101b]/95 border border-[#243047] rounded-lg p-0.5 text-[10px] font-mono">
          {(meshManifest?.lod_levels ?? [{ lod: 0 }, { lod: 1 }, { lod: 2 }]).map((l) => (
            <button
              key={l.lod}
              onClick={() => setActiveLod(l.lod)}
              className={`px-2 py-0.5 rounded transition-colors ${
                activeLod === l.lod
                  ? "bg-cyan-600 text-white font-semibold"
                  : "text-slate-400 hover:text-slate-200"
              }`}
              title={`Terrain mesh LOD ${l.lod}`}
            >
              LOD {l.lod}
            </button>
          ))}
        </div>

        {/* Surface Texture Overlay Mode */}
        <div className="flex bg-[#0b101b]/95 border border-[#243047] rounded-lg p-0.5 text-[10px] font-mono">
          {overlays.map((ov) => (
            <button
              key={ov.id}
              onClick={() => setActiveOverlayMode(ov.id)}
              className={`px-2 py-0.5 rounded transition-colors ${
                activeOverlayMode === ov.id
                  ? "bg-[#e25b38] text-white font-semibold"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {ov.label}
            </button>
          ))}
        </div>

        {/* Vertical Exaggeration Toggle */}
        <div
          className="flex bg-[#0b101b]/95 border border-[#243047] rounded-lg p-0.5 text-[10px] font-mono items-center"
          title="1x is true planetary scale; 2x/3x exaggerate relief visually only"
        >
          {[1, 2, 3].map((ex) => (
            <button
              key={ex}
              onClick={() => setVerticalExaggeration(ex)}
              className={`px-1.5 py-0.5 rounded transition-colors ${
                verticalExaggeration === ex
                  ? ex === 1
                    ? "bg-emerald-600 text-white font-semibold"
                    : "bg-amber-600 text-white font-semibold"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {ex}x{ex === 1 ? " True" : ""}
            </button>
          ))}
        </div>
      </div>

      {/* Top-Right Pick Mode & Camera Controls */}
      <div className="absolute top-2.5 right-2.5 z-10 flex flex-col items-end gap-1.5">
        {!compact && (
          <div className="flex bg-[#0b101b]/95 border border-[#243047] rounded-lg p-0.5 text-[10px] font-mono">
            {pickModes.map((pm) => {
              const Icon = pm.icon;
              const active = surfacePickMode === pm.id;
              return (
                <button
                  key={pm.id}
                  onClick={() => setSurfacePickMode(pm.id)}
                  className={`flex items-center gap-1 px-2 py-1 rounded transition-colors ${
                    active ? pm.activeClass : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Icon className="w-3 h-3" />
                  <span>{pm.label}</span>
                </button>
              );
            })}
          </div>
        )}

        <div className="flex items-center gap-1 bg-[#0b101b]/95 border border-[#243047] rounded-lg p-1 text-[10px] font-mono">
          <button
            onClick={() => requestCameraPreset("oblique")}
            className="px-2 py-0.5 rounded text-slate-300 hover:bg-[#182235]"
            title="Oblique terrain camera"
          >
            <Mountain className="w-3 h-3 inline mr-1" />
            Oblique
          </button>
          <button
            onClick={() => requestCameraPreset("top_down")}
            className="px-2 py-0.5 rounded text-slate-300 hover:bg-[#182235]"
            title="Top-down orthographic-like view"
          >
            <Compass className="w-3 h-3 inline mr-1" />
            Top
          </button>
          <button
            onClick={() => requestCameraPreset("focus_route")}
            disabled={!activeRoute}
            className="px-2 py-0.5 rounded text-cyan-300 hover:bg-[#182235] disabled:opacity-40"
            title="Focus active computed route"
          >
            <RouteIcon className="w-3 h-3 inline mr-1" />
            Route
          </button>
          <button
            onClick={() => setShowTargets((v) => !v)}
            className={`px-2 py-0.5 rounded transition-colors ${
              showTargets ? "bg-purple-500/20 text-purple-300" : "text-slate-400 hover:bg-[#182235]"
            }`}
            title="Toggle Science Target pins"
          >
            <Eye className="w-3 h-3 inline mr-1" />
            Targets
          </button>
        </div>
      </div>

      {/* Loading / Error State Overlay */}
      {(manifestLoading || tilesLoading) && (
        <div className="absolute top-14 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 bg-[#0d1424]/95 border border-cyan-500/40 rounded-full px-3 py-1 text-[11px] font-mono text-cyan-200 shadow-lg">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-cyan-400" />
          <span>
            {manifestLoading
              ? "Loading DEM 3D mesh manifest..."
              : `Streaming LOD ${activeLod} DEM tiles (${lodDescriptors.length})...`}
          </span>
        </div>
      )}

      {(manifestError || tileError) && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-[#07090f]/90 p-6">
          <div className="max-w-md bg-[#0e1525] border border-red-500/40 rounded-xl p-5 text-center space-y-3">
            <Layers className="w-7 h-7 text-red-400 mx-auto" />
            <div className="text-sm font-semibold text-red-200">
              3D Terrain Mesh Unavailable
            </div>
            <p className="text-xs text-slate-400">{manifestError || tileError}</p>
            <button
              onClick={() => void fetchMeshManifest(selectedDemDatasetId)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-xs font-medium text-white"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Retry Mesh Load
            </button>
          </div>
        </div>
      )}

      {/* Bottom Live Telemetry & DEM Metadata HUD */}
      <div className="absolute bottom-2.5 left-2.5 right-2.5 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        <div
          ref={hoverHudRef}
          className="bg-[#0b101b]/92 backdrop-blur border border-[#243047] rounded-lg px-2.5 py-1 text-[11px] font-mono text-slate-200 pointer-events-auto"
        >
          Hover valid DEM surface for telemetry · Drag to orbit · Right-drag to pan · Wheel to zoom
        </div>

        <div className="flex items-center gap-2 bg-[#0b101b]/92 backdrop-blur border border-[#243047] rounded-lg px-2.5 py-1 text-[10px] font-mono text-slate-400 pointer-events-auto">
          <span className="text-slate-200">
            {meshManifest?.product_id || selectedDemDatasetId}
          </span>
          <span>|</span>
          <span>
            {meshManifest?.native_resolution_m
              ? `${meshManifest.native_resolution_m.toFixed(2)} m/px`
              : "DEM"}
          </span>
          <span>|</span>
          <span>{tilesLoadedCount} tiles / {renderedVertexTotal.toLocaleString()} valid pts</span>
          <span>|</span>
          <span className={verticalExaggeration === 1 ? "text-emerald-300" : "text-amber-300"}>
            {verticalExaggeration === 1 ? "1x True Scale" : `${verticalExaggeration}x Exag (Visual)`}
          </span>
        </div>
      </div>
    </div>
  );
}
