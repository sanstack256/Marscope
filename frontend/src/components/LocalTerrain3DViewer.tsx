"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  Compass,
  Crosshair,
  Eye,
  Flag,
  Grid,
  Layers,
  Loader2,
  MapPin,
  Mountain,
  RefreshCw,
  Route as RouteIcon,
  Target,
} from "lucide-react";
import { API_BASE_URL } from "@/lib/constants";
import { useEvaOperationsStore } from "@/stores/useEvaOperationsStore";
import { useEvidenceStore } from "@/stores/useEvidenceStore";
import { useRoutingStore, type CameraPresetType } from "@/stores/useRoutingStore";
import type {
  PickedSurfacePoint,
  ScienceTarget,
  SurfacePickMode,
  TerrainMeshManifest,
  TerrainMeshTile,
  TextureOverlayMode,
} from "@/types";

const TERRAIN_TEX_SIZE = 512;

export type BeaconMarkerShape = "start" | "destination" | "waypoint" | "target";

/**
 * Shared marker head silhouette mapping.
 * Start and Destination intentionally share the identical spherical pin silhouette
 * and proportions; directional arrows belong strictly to the route polyline.
 */
export function getMarkerHeadGeometryKind(
  shape: BeaconMarkerShape
): "sphere" | "box" | "octahedron" {
  if (shape === "waypoint") return "box";
  if (shape === "target") return "octahedron";
  return "sphere";
}

function buildTileTextureUrl(
  tile: TerrainMeshTile,
  manifest: TerrainMeshManifest,
  overlayMode: TextureOverlayMode
): string {
  const texDatasetId =
    overlayMode === "ortho" && manifest.ortho_dataset_id
      ? manifest.ortho_dataset_id
      : manifest.dataset_id;
  const texOverlay: TextureOverlayMode =
    overlayMode === "ortho" && !manifest.ortho_dataset_id ? "elevation" : overlayMode;

  const qs = new URLSearchParams({
    overlay: texOverlay,
    min_lat: tile.bounds.min_lat.toFixed(7),
    max_lat: tile.bounds.max_lat.toFixed(7),
    min_lon: tile.bounds.min_lon.toFixed(7),
    max_lon: tile.bounds.max_lon.toFixed(7),
    size: String(TERRAIN_TEX_SIZE),
  });
  if (texOverlay === "elevation" && manifest.elevation_range_m) {
    qs.set("vmin", String(manifest.elevation_range_m.min_m));
    qs.set("vmax", String(manifest.elevation_range_m.max_m));
  } else if (texOverlay === "roughness" && manifest.roughness_range_m) {
    qs.set("vmin", String(manifest.roughness_range_m.min_m));
    qs.set("vmax", String(manifest.roughness_range_m.max_m));
  }
  return `${API_BASE_URL}/terrain/ortho/${encodeURIComponent(texDatasetId)}/texture?${qs.toString()}`;
}

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

export interface LivePositionMarker {
  lat: number;
  lon_east: number;
  elevation_m?: number | null;
  off_route?: boolean;
  heading_deg?: number | null;
}

interface LocalTerrain3DViewerProps {
  targets?: ScienceTarget[];
  simulationProgressM?: number | null;
  livePositionMarker?: LivePositionMarker | null;
  onSurfaceInspect?: (point: PickedSurfacePoint) => void;
  compact?: boolean;
}

export function LocalTerrain3DViewer({
  targets = [],
  simulationProgressM = null,
  livePositionMarker = null,
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
  const tileBoundsGroupRef = useRef<THREE.Group | null>(null);
  const refElevMRef = useRef<number>(-4500);
  const sceneInitializedRef = useRef<boolean>(false);
  const fittedManifestKeyRef = useRef<string>("");
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
  const zoomAdaptiveMarkersRef = useRef<Array<{ obj: THREE.Object3D; weight: number }>>([]);
  const [overviewClusterMode, setOverviewClusterMode] = useState(false);
  const overviewClusterRef = useRef(false);

  const [tilesLoading, setTilesLoading] = useState(false);
  const [tilesLoadedCount, setTilesLoadedCount] = useState(0);
  const [tileError, setTileError] = useState<string | null>(null);
  const [showTargets, setShowTargets] = useState(true);
  const [showRoute, setShowRoute] = useState(true);
  const [showTileBoundaries, setShowTileBoundaries] = useState(false);
  const [lodMode, setLodMode] = useState<"auto" | "manual">("auto");
  const [renderedVertexTotal, setRenderedVertexTotal] = useState(0);
  const [pendingPickConfirm, setPendingPickConfirm] = useState<{
    mode: "set_start" | "set_destination";
    point: PickedSurfacePoint;
  } | null>(null);

  const selectedDemDatasetId = useRoutingStore((s) => s.selectedDemDatasetId);
  const meshManifest = useRoutingStore((s) => s.meshManifest);
  const manifestLoading = useRoutingStore((s) => s.manifestLoading);
  const manifestError = useRoutingStore((s) => s.manifestError);
  const activeLod = useRoutingStore((s) => s.activeLod);
  const activeOverlayMode = useRoutingStore((s) => s.activeOverlayMode);
  const verticalExaggeration = useRoutingStore((s) => s.verticalExaggeration);
  const surfacePickMode = useRoutingStore((s) => s.surfacePickMode);
  const corridorAssessment = useEvidenceStore((s) => s.corridorAssessment);
  const evidenceOverlays = useEvidenceStore((s) => s.overlays);
  const selectedSegmentId = useEvidenceStore((s) => s.selectedSegmentId);
  const evaReturnPlan = useEvaOperationsStore((s) => s.evaEnvelope?.return_plan ?? null);
  const startPoint = useRoutingStore((s) => s.startPoint);
  const destinationPoint = useRoutingStore((s) => s.destinationPoint);
  const customWaypoints = useRoutingStore((s) => s.customWaypoints);
  const selectedTargetIds = useRoutingStore((s) => s.selectedTargetIds);
  const activeRoute = useRoutingStore((s) => s.activeRoute);
  const staleRoute = useRoutingStore((s) => s.staleRoute);
  const staleReason = useRoutingStore((s) => s.staleReason);
  const selectedWaypointSeq = useRoutingStore((s) => s.selectedWaypointSeq);
  const selectedInstructionStep = useRoutingStore((s) => s.selectedInstructionStep);
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
    controls.dampingFactor = 0.085;
    controls.screenSpacePanning = false;
    controls.minPolarAngle = 0.04;
    controls.maxPolarAngle = Math.PI * 0.485;
    controls.minDistance = 15;
    controls.maxDistance = 45000;
    controls.target.set(0, 0, 0);

    controls.addEventListener("start", () => {
      cameraAnimRef.current = null;
    });

    // Physically grounded Martian directional lighting + soft dust bounce ambient (no specular glare)
    const ambient = new THREE.AmbientLight("#5c4338", 0.58);
    const hemi = new THREE.HemisphereLight("#e8c8ae", "#231915", 0.62);
    const sun = new THREE.DirectionalLight("#f7e3ce", 1.5);
    sun.position.set(2200, 3200, 1400);
    const fill = new THREE.DirectionalLight("#7aa2cc", 0.25);
    fill.position.set(-1800, 1200, -1600);
    scene.add(ambient, hemi, sun, fill);

    const terrainGroup = new THREE.Group();
    const overlayGroup = new THREE.Group();
    const tileBoundsGroup = new THREE.Group();
    scene.add(terrainGroup);
    scene.add(tileBoundsGroup);
    scene.add(overlayGroup);

    rendererRef.current = renderer;
    sceneRef.current = scene;
    cameraRef.current = camera;
    controlsRef.current = controls;
    terrainGroupRef.current = terrainGroup;
    tileBoundsGroupRef.current = tileBoundsGroup;
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
        if (st.startPoint) {
          setPendingPickConfirm({ mode: "set_start", point: picked });
        } else {
          st.setStartPoint({
            lat: picked.lat,
            lon_east: picked.lon_east,
            label: `Start (${picked.lat.toFixed(4)}°, ${picked.lon_east.toFixed(4)}°)`,
          });
          st.setSurfacePickMode("inspect");
        }
      } else if (st.surfacePickMode === "set_destination") {
        if (st.destinationPoint) {
          setPendingPickConfirm({ mode: "set_destination", point: picked });
        } else {
          st.setDestinationPoint({
            lat: picked.lat,
            lon_east: picked.lon_east,
            label: `Dest (${picked.lat.toFixed(4)}°, ${picked.lon_east.toFixed(4)}°)`,
          });
          st.setSurfacePickMode("inspect");
        }
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

      // Zoom-adaptive marker scaling: preserve exact geographic anchor while keeping
      // apparent screen size controlled across close-up and overview camera distances.
      const camDistTarget = camera.position.distanceTo(controls.target);
      const shouldCluster = camDistTarget > 2400;
      if (shouldCluster !== overviewClusterRef.current) {
        overviewClusterRef.current = shouldCluster;
        setOverviewClusterMode(shouldCluster);
      }
      const markers = zoomAdaptiveMarkersRef.current;
      for (let i = 0; i < markers.length; i += 1) {
        const m = markers[i];
        const d = camera.position.distanceTo(m.obj.position);
        const s = Math.max(1.2, Math.min(65.0, d * 0.015)) * m.weight;
        m.obj.scale.setScalar(s);
      }

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

  const activeOverlayRef = useRef<TextureOverlayMode>(activeOverlayMode);
  useEffect(() => {
    activeOverlayRef.current = activeOverlayMode;
  }, [activeOverlayMode]);

  // Auto-LOD distance selector: adjusts LOD smoothly based on camera distance when lodMode === "auto"
  useEffect(() => {
    const controls = controlsRef.current;
    const camera = cameraRef.current;
    if (!controls || !camera || !meshManifest || lodMode !== "auto") return;

    const wM = meshManifest.physical_extent_m.width_m || 2000;
    const hM = meshManifest.physical_extent_m.height_m || 2000;
    const span = Math.max(wM, hM, 400);
    const maxAvailLod = Math.max(0, ...meshManifest.lod_levels.map((l) => l.lod));
    let timerId: number | null = null;

    const evaluateAutoLod = () => {
      if (timerId !== null) window.clearTimeout(timerId);
      timerId = window.setTimeout(() => {
        const dist = camera.position.distanceTo(controls.target);
        let desired = 1;
        if (dist > span * 1.45) desired = 0;
        else if (dist < span * 0.72) desired = Math.min(2, maxAvailLod);
        else desired = Math.min(1, maxAvailLod);
        if (desired !== useRoutingStore.getState().activeLod) {
          setActiveLod(desired);
        }
      }, 220);
    };

    controls.addEventListener("change", evaluateAutoLod);
    return () => {
      controls.removeEventListener("change", evaluateAutoLod);
      if (timerId !== null) window.clearTimeout(timerId);
    };
  }, [meshManifest, lodMode, setActiveLod]);

  // Load DEM mesh geometry (decoupled from activeOverlayMode so texture swaps never reload geometry or reset camera)
  useEffect(() => {
    const terrainGroup = terrainGroupRef.current;
    if (!meshManifest || !terrainGroup || lodDescriptors.length === 0) return;

    const controller = new AbortController();
    let cancelled = false;
    setTilesLoading(true);
    setTileError(null);

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
            const cacheKey = `${meshManifest.dataset_id}:${desc.tile_id}:${desc.grid_cols}`;
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
            if (tileCacheRef.current.size > 64) {
              const firstKey = tileCacheRef.current.keys().next().value;
              if (firstKey) tileCacheRef.current.delete(firstKey);
            }
            return data;
          })
        );

        if (cancelled || !terrainGroupRef.current) return;

        // Establish stable local elevation baseline across loaded tiles
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
        const currentOverlay = activeOverlayRef.current;

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

              // Half-texel inset aligns adjacent tile boundary pixels without bilinear edge seams
              uvs[idx * 2] = (0.5 + uFrac * (TERRAIN_TEX_SIZE - 1)) / TERRAIN_TEX_SIZE;
              uvs[idx * 2 + 1] = 1 - (0.5 + vFrac * (TERRAIN_TEX_SIZE - 1)) / TERRAIN_TEX_SIZE;
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

              if (va && vsw && vb) indices.push(a, sw, b);
              if (vb && vsw && vse) indices.push(b, sw, se);
            }
          }

          if (indices.length === 0) return;
          totalVerts += tile.valid_vertex_count;

          const geom = new THREE.BufferGeometry();
          geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
          geom.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
          geom.setIndex(indices);
          if (tile.normals && tile.normals.length === numVerts * 3) {
            geom.setAttribute("normal", new THREE.BufferAttribute(new Float32Array(tile.normals), 3));
          } else {
            geom.computeVertexNormals();
          }
          geom.computeBoundingBox();
          geom.computeBoundingSphere();

          const mat = new THREE.MeshStandardMaterial({
            color: new THREE.Color("#9e7a66"),
            roughness: 0.92,
            metalness: 0.02,
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

          const texUrl = buildTileTextureUrl(tile, meshManifest, currentOverlay);
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
                if (textureCacheRef.current.size > 64) {
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

        // Auto-fit camera ONLY when DEM dataset or region bounds change (preserve focus on LOD/overlay switches)
        const manifestKey = `${meshManifest.dataset_id}:${meshManifest.requested_bounds.min_lat}:${meshManifest.requested_bounds.max_lat}:${meshManifest.requested_bounds.min_lon}:${meshManifest.requested_bounds.max_lon}`;
        if (manifestKey !== fittedManifestKeyRef.current) {
          fittedManifestKeyRef.current = manifestKey;
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
  }, [meshManifest, activeLod, lodDescriptors, animateCameraTo]);

  // Hot-swap texture overlays cleanly without tearing down mesh geometry or resetting camera
  useEffect(() => {
    const terrainGroup = terrainGroupRef.current;
    if (!terrainGroup || !meshManifest || tilesLoadedCount === 0) return;

    let cancelled = false;
    const texLoader = new THREE.TextureLoader();

    terrainGroup.children.forEach((child) => {
      const mesh = child as THREE.Mesh;
      const ud = mesh.userData as TileMeshUserData | undefined;
      if (!ud?.tile) return;
      const mat = mesh.material as THREE.MeshStandardMaterial;
      const texUrl = buildTileTextureUrl(ud.tile, meshManifest, activeOverlayMode);

      const cached = textureCacheRef.current.get(texUrl);
      if (cached) {
        mat.color.set("#ffffff");
        mat.map = cached;
        mat.needsUpdate = true;
        return;
      }

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
          if (textureCacheRef.current.size > 64) {
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
          // Keep current shading if texture fails
        }
      );
    });

    return () => {
      cancelled = true;
    };
  }, [activeOverlayMode, meshManifest, tilesLoadedCount]);

  // Diagnostic tile boundaries overlay (strictly OFF by default; toggleable for verification)
  useEffect(() => {
    const boundsGroup = tileBoundsGroupRef.current;
    const terrainGroup = terrainGroupRef.current;
    if (!boundsGroup || !terrainGroup || !meshManifest) return;

    while (boundsGroup.children.length > 0) {
      const obj = boundsGroup.children[boundsGroup.children.length - 1] as THREE.Line;
      boundsGroup.remove(obj);
      if (obj.geometry) obj.geometry.dispose();
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
      mats.forEach((m) => m?.dispose());
    }
    if (!showTileBoundaries) return;

    const exag = verticalExaggeration;
    const refElev = refElevMRef.current;
    terrainGroup.children.forEach((child) => {
      const mesh = child as THREE.Mesh;
      const ud = mesh.userData as TileMeshUserData | undefined;
      if (!ud?.tile) return;
      const t = ud.tile;
      const rows = t.grid_rows;
      const cols = t.grid_cols;
      const pts: THREE.Vector3[] = [];
      const pushRc = (r: number, c: number) => {
        const idx = r * cols + c;
        const vFrac = rows > 1 ? r / (rows - 1) : 0;
        const uFrac = cols > 1 ? c / (cols - 1) : 0;
        const eastM = ud.minEastM + uFrac * (ud.maxEastM - ud.minEastM);
        const northM = ud.maxNorthM - vFrac * (ud.maxNorthM - ud.minNorthM);
        const zVal = t.valid_mask[idx] === 1 && t.elevations_m[idx] != null ? (t.elevations_m[idx] as number) : refElev;
        pts.push(new THREE.Vector3(eastM, (zVal - refElev) * exag + 2.5, -northM));
      };
      for (let c = 0; c < cols; c += 1) pushRc(0, c);
      for (let r = 1; r < rows; r += 1) pushRc(r, cols - 1);
      for (let c = cols - 2; c >= 0; c -= 1) pushRc(rows - 1, c);
      for (let r = rows - 2; r >= 0; r -= 1) pushRc(r, 0);

      const lineGeom = new THREE.BufferGeometry().setFromPoints(pts);
      const lineMat = new THREE.LineBasicMaterial({ color: "#38bdf8", transparent: true, opacity: 0.75 });
      boundsGroup.add(new THREE.Line(lineGeom, lineMat));
    });
  }, [showTileBoundaries, meshManifest, verticalExaggeration, tilesLoadedCount]);

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
    zoomAdaptiveMarkersRef.current = [];
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
      userData: Record<string, unknown> = {},
      shape: "start" | "destination" | "waypoint" | "target" = "target"
    ) => {
      const markerGroup = new THREE.Group();
      markerGroup.position.copy(pos);

      const poleHeight = 2.2;
      const stemGeom = new THREE.CylinderGeometry(0.14, 0.14, poleHeight, 8);
      const stemMat = new THREE.MeshBasicMaterial({ color: colorHex });
      const stem = new THREE.Mesh(stemGeom, stemMat);
      stem.position.set(0, poleHeight * 0.5, 0);
      stem.userData = userData;

      const headKind = getMarkerHeadGeometryKind(shape);
      let headGeom: THREE.BufferGeometry;
      if (headKind === "box") {
        headGeom = new THREE.BoxGeometry(0.72, 0.72, 0.72);
      } else if (headKind === "octahedron") {
        headGeom = new THREE.OctahedronGeometry(0.56, 0);
      } else {
        headGeom = new THREE.SphereGeometry(0.52, 14, 14);
      }
      const headMat = new THREE.MeshBasicMaterial({ color: colorHex });
      const head = new THREE.Mesh(headGeom, headMat);
      head.position.set(0, poleHeight, 0);
      head.userData = userData;

      markerGroup.add(stem, head);
      overlayGroup.add(markerGroup);
      zoomAdaptiveMarkersRef.current.push({ obj: markerGroup, weight: radiusScale });
    };

    // Render Science Targets inside DEM bounds (with overview-zoom density clustering)
    if (showTargets && targets.length > 0) {
      const b = meshManifest.requested_bounds;
      const inBoundsTargets = targets.filter(
        (t) =>
          t.latitude >= b.min_lat - 0.01 &&
          t.latitude <= b.max_lat + 0.01 &&
          t.longitude >= b.min_lon - 0.01 &&
          t.longitude <= b.max_lon + 0.01
      );
      const placedClusters: Array<{ eastM: number; northM: number }> = [];
      inBoundsTargets.forEach((t) => {
        const selected = selectedTargetIds.includes(t.id);
        const { eastM, northM } = latLonToLocalMeters(t.latitude, t.longitude, originLat, originLon);
        if (overviewClusterMode && !selected) {
          const tooClose = placedClusters.some(
            (c) => Math.hypot(c.eastM - eastM, c.northM - northM) < 95
          );
          if (tooClose) return;
          placedClusters.push({ eastM, northM });
        }
        const elev = t.elevation_m ?? lookupElevNear(t.latitude, t.longitude);
        const pos = toSceneVec(t.latitude, t.longitude, elev, 2);
        addBeaconPin(
          pos,
          selected ? "#fde047" : "#a855f7",
          selected ? 1.25 : 0.85,
          { kind: "science_target", targetId: t.id },
          "target"
        );
      });
    }

    // Render custom waypoints
    customWaypoints.forEach((wp) => {
      const elev = lookupElevNear(wp.lat, wp.lon_east);
      const pos = toSceneVec(wp.lat, wp.lon_east, elev, 2);
      addBeaconPin(pos, "#f59e0b", 0.95, { kind: "custom_waypoint" }, "waypoint");
    });

    // Render explicit Start & Destination markers
    if (startPoint) {
      const elev = activeRoute?.vertices[0]?.elevation_m ?? lookupElevNear(startPoint.lat, startPoint.lon_east);
      addBeaconPin(
        toSceneVec(startPoint.lat, startPoint.lon_east, elev, 2),
        "#10b981",
        1.3,
        { kind: "start" },
        "start"
      );
    }
    if (destinationPoint) {
      const elev = lookupElevNear(destinationPoint.lat, destinationPoint.lon_east);
      addBeaconPin(
        toSceneVec(destinationPoint.lat, destinationPoint.lon_east, elev, 2),
        "#f43f5e",
        1.3,
        { kind: "destination" },
        "destination"
      );
    }

    // Render Active Route exact piecewise polyline (NO CatmullRomCurve3 smoothing) + Return Leg + Cones + Selected Segment
    if (showRoute && activeRoute && activeRoute.vertices.length >= 2) {
      const returnLegStartSeq =
        activeRoute.legs.find((l) => l.is_return_leg)?.vertex_start_seq ?? Number.POSITIVE_INFINITY;
      const activeInstr =
        selectedInstructionStep != null
          ? activeRoute.instructions.find((ins) => ins.step_index === selectedInstructionStep)
          : undefined;
      const upVec = new THREE.Vector3(0, 1, 0);
      const radius = pinScale * 0.24;

      const buildExactPolyline = (vertsSubset: typeof activeRoute.vertices, colorHex: string) => {
        if (vertsSubset.length < 2) return;
        const pts = vertsSubset.map((v) => toSceneVec(v.lat, v.lon_east, v.elevation_m, 3.5));

        // Exact sharp-vertex 3D core line
        const lineGeom = new THREE.BufferGeometry().setFromPoints(pts);
        const lineMat = new THREE.LineBasicMaterial({ color: colorHex });
        overlayGroup.add(new THREE.Line(lineGeom, lineMat));

        const segMat = new THREE.MeshStandardMaterial({
          color: colorHex,
          emissive: colorHex,
          emissiveIntensity: 0.42,
          roughness: 0.35,
        });
        const highlightMat = new THREE.MeshStandardMaterial({
          color: "#fde047",
          emissive: "#facc15",
          emissiveIntensity: 0.75,
          roughness: 0.25,
        });

        for (let i = 0; i < pts.length - 1; i += 1) {
          const p0 = pts[i];
          const p1 = pts[i + 1];
          const segVec = new THREE.Vector3().subVectors(p1, p0);
          const len = segVec.length();
          if (len < 1e-4) continue;
          const v0 = vertsSubset[i];
          const v1 = vertsSubset[i + 1];
          const instrStartCum =
            activeInstr != null ? activeInstr.cumulative_distance_m - activeInstr.segment_distance_m : 0;
          const isHighlighted =
            (selectedWaypointSeq != null && (selectedWaypointSeq === v0.seq || selectedWaypointSeq === v1.seq)) ||
            (activeInstr != null &&
              activeInstr.segment_distance_m > 0 &&
              v1.cumulative_distance_m > instrStartCum + 0.05 &&
              v0.cumulative_distance_m < activeInstr.cumulative_distance_m - 0.05);
          const r = isHighlighted ? radius * 1.55 : radius;
          const cylGeom = new THREE.CylinderGeometry(r, r, len, 8, 1);
          const cyl = new THREE.Mesh(cylGeom, isHighlighted ? highlightMat : segMat);
          cyl.position.copy(p0).add(p1).multiplyScalar(0.5);
          cyl.quaternion.setFromUnitVectors(upVec, segVec.normalize());
          overlayGroup.add(cyl);

          // Spherical joint cap at exact vertex position to avoid miter gaps
          const joint = new THREE.Mesh(new THREE.SphereGeometry(r, 8, 8), isHighlighted ? highlightMat : segMat);
          joint.position.copy(p0);
          overlayGroup.add(joint);
        }
      };

      const outboundVerts = activeRoute.vertices.filter((v) => v.seq <= returnLegStartSeq);
      const returnVerts = activeRoute.vertices.filter((v) => v.seq >= returnLegStartSeq);

      buildExactPolyline(outboundVerts, "#38bdf8");
      if (returnVerts.length >= 2) {
        buildExactPolyline(returnVerts, "#fb923c");
      }

      // 3D directional heading cones along straight exact segments
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

      // Clickable route stop spheres + selected waypoint halo ring (zoom-adaptive)
      activeRoute.vertices
        .filter((v) => v.is_stop || selectedWaypointSeq === v.seq)
        .forEach((v) => {
          const isSel = selectedWaypointSeq === v.seq;
          const pos = toSceneVec(v.lat, v.lon_east, v.elevation_m, 5.5);
          const stopGroup = new THREE.Group();
          stopGroup.position.copy(pos);

          const orbGeom = new THREE.SphereGeometry(isSel ? 0.65 : 0.42, 14, 14);
          const orbMat = new THREE.MeshBasicMaterial({
            color: isSel ? "#fde047" : "#38bdf8",
          });
          const orb = new THREE.Mesh(orbGeom, orbMat);
          orb.userData = { kind: "route_waypoint", waypointSeq: v.seq };
          stopGroup.add(orb);

          if (isSel) {
            const ringGeom = new THREE.RingGeometry(0.9, 1.35, 24);
            const ringMat = new THREE.MeshBasicMaterial({
              color: "#fde047",
              side: THREE.DoubleSide,
            });
            const ring = new THREE.Mesh(ringGeom, ringMat);
            ring.rotation.x = -Math.PI / 2;
            ring.position.set(0, 0.25, 0);
            stopGroup.add(ring);
          }
          overlayGroup.add(stopGroup);
          zoomAdaptiveMarkersRef.current.push({ obj: stopGroup, weight: isSel ? 1.15 : 0.85 });
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
        const roverGroup = new THREE.Group();
        roverGroup.position.copy(astroPos);
        const roverGeom = new THREE.OctahedronGeometry(0.85, 0);
        const roverMat = new THREE.MeshStandardMaterial({
          color: "#22d3ee",
          emissive: "#06b6d4",
          emissiveIntensity: 0.75,
          wireframe: true,
        });
        const roverMesh = new THREE.Mesh(roverGeom, roverMat);
        roverGroup.add(roverMesh);
        overlayGroup.add(roverGroup);
        zoomAdaptiveMarkersRef.current.push({ obj: roverGroup, weight: 1.0 });
      }
    }

    // Authenticated Live Mission Telemetry Beacon (strictly rendered only from authenticated live fixes)
    if (livePositionMarker) {
      const liveElev =
        livePositionMarker.elevation_m ??
        lookupElevNear(livePositionMarker.lat, livePositionMarker.lon_east);
      const livePos = toSceneVec(livePositionMarker.lat, livePositionMarker.lon_east, liveElev, 7);
      const beaconColor = livePositionMarker.off_route ? "#ef4444" : "#10b981";
      const liveGroup = new THREE.Group();
      liveGroup.position.copy(livePos);

      const liveRingGeom = new THREE.RingGeometry(1.15, 1.65, 24);
      const liveRingMat = new THREE.MeshBasicMaterial({
        color: beaconColor,
        side: THREE.DoubleSide,
      });
      const liveRing = new THREE.Mesh(liveRingGeom, liveRingMat);
      liveRing.rotation.x = -Math.PI / 2;
      liveRing.position.set(0, -0.5, 0);
      liveGroup.add(liveRing);

      const liveCore = new THREE.Mesh(
        new THREE.SphereGeometry(0.72, 14, 14),
        new THREE.MeshStandardMaterial({
          color: beaconColor,
          emissive: beaconColor,
          emissiveIntensity: 0.9,
        })
      );
      liveGroup.add(liveCore);
      overlayGroup.add(liveGroup);
      zoomAdaptiveMarkersRef.current.push({ obj: liveGroup, weight: 1.0 });
    }

    // Evidence Intelligence Corridor, Segments, Gaps, Candidates & Observations
    if (corridorAssessment && corridorAssessment.dataset_id === meshManifest.dataset_id) {
      if (evidenceOverlays.showCorridor) {
        const drawBoundary = (pts: number[][], colorHex: string, opacityVal = 0.78) => {
          if (pts.length < 2) return;
          const vecs = pts.map(([lon, lat]) => {
            const elev = lookupElevNear(lat, lon);
            return toSceneVec(lat, lon, elev, 2.5);
          });
          const g = new THREE.BufferGeometry().setFromPoints(vecs);
          const m = new THREE.LineBasicMaterial({ color: colorHex, transparent: true, opacity: opacityVal });
          overlayGroup.add(new THREE.Line(g, m));
        };
        if (
          corridorAssessment.corridor_geometry.polygon_ring &&
          corridorAssessment.corridor_geometry.polygon_ring.length >= 4
        ) {
          drawBoundary(corridorAssessment.corridor_geometry.polygon_ring, "#22d3ee", 0.82);
        } else {
          drawBoundary(corridorAssessment.corridor_geometry.left_boundary, "#22d3ee");
          drawBoundary(corridorAssessment.corridor_geometry.right_boundary, "#22d3ee");
        }
      }

      if (evidenceOverlays.showSegments) {
        corridorAssessment.segments.forEach((seg) => {
          const isSel = selectedSegmentId === seg.segment_id;
          if (isSel && seg.corridor_polygon && seg.corridor_polygon.length >= 4) {
            const ringPts = seg.corridor_polygon.map(([lon, lat]) =>
              toSceneVec(lat, lon, lookupElevNear(lat, lon), 3.4)
            );
            const rg = new THREE.BufferGeometry().setFromPoints(ringPts);
            overlayGroup.add(
              new THREE.Line(rg, new THREE.LineBasicMaterial({ color: "#facc15", transparent: true, opacity: 0.96 }))
            );
          }
          const elev = lookupElevNear(seg.end_coord.lat, seg.end_coord.lon_east);
          const pos = toSceneVec(seg.end_coord.lat, seg.end_coord.lon_east, elev, 4.5);
          const m = new THREE.Mesh(
            new THREE.BoxGeometry(isSel ? 0.9 : 0.55, isSel ? 0.9 : 0.55, isSel ? 0.9 : 0.55),
            new THREE.MeshBasicMaterial({ color: isSel ? "#facc15" : "#38bdf8" })
          );
          m.position.copy(pos);
          overlayGroup.add(m);
          zoomAdaptiveMarkersRef.current.push({ obj: m, weight: isSel ? 1.1 : 0.75 });
        });
      }

      if (
        evaReturnPlan &&
        evaReturnPlan.return_route_computed &&
        evidenceOverlays.showReturnRoute &&
        evaReturnPlan.return_route_vertices.length >= 2
      ) {
        const retVecs = evaReturnPlan.return_route_vertices.map((rv) =>
          toSceneVec(rv.lat, rv.lon_east, rv.elevation_m, 4.2)
        );
        const rg = new THREE.BufferGeometry().setFromPoints(retVecs);
        const rm = new THREE.LineDashedMaterial({
          color: "#fb7185",
          dashSize: 1.6,
          gapSize: 0.9,
          transparent: true,
          opacity: 0.92,
        });
        const rLine = new THREE.Line(rg, rm);
        rLine.computeLineDistances();
        overlayGroup.add(rLine);
      }

      if (evidenceOverlays.showGaps) {
        corridorAssessment.evidence_gaps.slice(0, 24).forEach((gap) => {
          const b = gap.bounds;
          if (b.min_lat == null || b.max_lat == null || b.min_lon == null || b.max_lon == null) return;
          const corners = [
            [b.min_lat, b.min_lon],
            [b.min_lat, b.max_lon],
            [b.max_lat, b.max_lon],
            [b.max_lat, b.min_lon],
            [b.min_lat, b.min_lon],
          ].map(([lt, ln]) => toSceneVec(lt, ln, lookupElevNear(lt, ln), 3.0));
          const g = new THREE.BufferGeometry().setFromPoints(corners);
          const m = new THREE.LineBasicMaterial({ color: "#f59e0b", transparent: true, opacity: 0.75 });
          overlayGroup.add(new THREE.Line(g, m));
        });
      }

      if (evidenceOverlays.showTerrainCandidates) {
        corridorAssessment.terrain_candidates.slice(0, 25).forEach((tc) => {
          const pos = toSceneVec(
            tc.latitude,
            tc.longitude_east,
            tc.geometric_measurements.elevation_m ?? lookupElevNear(tc.latitude, tc.longitude_east),
            5.0
          );
          const m = new THREE.Mesh(
            new THREE.OctahedronGeometry(0.55, 0),
            new THREE.MeshBasicMaterial({ color: "#fb923c" })
          );
          m.position.copy(pos);
          overlayGroup.add(m);
          zoomAdaptiveMarkersRef.current.push({ obj: m, weight: 0.8 });
        });
      }

      if (evidenceOverlays.showOpticalCandidates) {
        corridorAssessment.optical_candidates.slice(0, 25).forEach((oc) => {
          const pos = toSceneVec(oc.latitude, oc.longitude_east, lookupElevNear(oc.latitude, oc.longitude_east), 5.5);
          const m = new THREE.Mesh(
            new THREE.OctahedronGeometry(0.5, 0),
            new THREE.MeshBasicMaterial({ color: "#e879f9" })
          );
          m.position.copy(pos);
          overlayGroup.add(m);
          zoomAdaptiveMarkersRef.current.push({ obj: m, weight: 0.75 });
        });
      }

      if (evidenceOverlays.showObservations) {
        corridorAssessment.observations.slice(0, 30).forEach((obs) => {
          if (obs.latitude == null || obs.longitude_east == null) return;
          const pos = toSceneVec(
            obs.latitude,
            obs.longitude_east,
            lookupElevNear(obs.latitude, obs.longitude_east),
            5.5
          );
          const m = new THREE.Mesh(
            new THREE.SphereGeometry(0.5, 10, 10),
            new THREE.MeshBasicMaterial({ color: "#34d399" })
          );
          m.position.copy(pos);
          overlayGroup.add(m);
          zoomAdaptiveMarkersRef.current.push({ obj: m, weight: 0.8 });
        });
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
    selectedInstructionStep,
    showRoute,
    overviewClusterMode,
    simulationProgressM,
    livePositionMarker,
    tilesLoadedCount,
    corridorAssessment,
    evidenceOverlays,
    selectedSegmentId,
    evaReturnPlan,
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

  // Respond to camera presets (`oblique`, `top_down`, `focus_start`, `focus_destination`, `focus_route`, `reset`)
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
    } else if (preset === "focus_start" && startPoint) {
      const { eastM, northM } = latLonToLocalMeters(
        startPoint.lat,
        startPoint.lon_east,
        meshManifest.origin.lat,
        meshManifest.origin.lon_east
      );
      const yBase =
        activeRoute?.vertices[0] != null
          ? (activeRoute.vertices[0].elevation_m - refElevMRef.current) * verticalExaggeration
          : 0;
      const off = Math.max(180, span * 0.16);
      animateCameraTo(
        new THREE.Vector3(eastM + off * 0.65, yBase + off * 0.85, -northM + off * 0.75),
        new THREE.Vector3(eastM, yBase, -northM),
        480
      );
    } else if (preset === "focus_destination" && destinationPoint) {
      const { eastM, northM } = latLonToLocalMeters(
        destinationPoint.lat,
        destinationPoint.lon_east,
        meshManifest.origin.lat,
        meshManifest.origin.lon_east
      );
      const lastV = activeRoute?.vertices[activeRoute.vertices.length - 1];
      const yBase = lastV != null ? (lastV.elevation_m - refElevMRef.current) * verticalExaggeration : 0;
      const off = Math.max(180, span * 0.16);
      animateCameraTo(
        new THREE.Vector3(eastM + off * 0.65, yBase + off * 0.85, -northM + off * 0.75),
        new THREE.Vector3(eastM, yBase, -northM),
        480
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
  }, [cameraPresetRequest, meshManifest, activeRoute, startPoint, destinationPoint, verticalExaggeration, animateCameraTo]);

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

      {/* Unified Non-Overlapping Top HUD Controls (Left: DEM/LOD/Overlay/Scale · Right: Pick/Camera) */}
      <div className="absolute top-2.5 left-2.5 right-2.5 z-10 flex flex-wrap items-start justify-between gap-1.5 pointer-events-none">
        <div className="flex flex-wrap items-center gap-1.5 pointer-events-auto">
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

        {/* Adaptive / Manual LOD Selector */}
        <div className="flex bg-[#0b101b]/95 border border-[#243047] rounded-lg p-0.5 text-[10px] font-mono">
          <button
            onClick={() => setLodMode("auto")}
            className={`px-2 py-0.5 rounded transition-colors ${
              lodMode === "auto"
                ? "bg-emerald-600 text-white font-semibold"
                : "text-slate-400 hover:text-slate-200"
            }`}
            title="Adaptive camera-distance LOD"
          >
            Auto
          </button>
          {(meshManifest?.lod_levels ?? [{ lod: 0 }, { lod: 1 }, { lod: 2 }]).map((l) => (
            <button
              key={l.lod}
              onClick={() => {
                setLodMode("manual");
                setActiveLod(l.lod);
              }}
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

      {/* Pick Mode & Camera Controls */}
        <div className="flex flex-wrap items-center justify-end gap-1.5 pointer-events-auto">
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

        <div className="flex flex-wrap items-center gap-1 bg-[#0b101b]/95 border border-[#243047] rounded-lg p-1 text-[10px] font-mono">
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
            onClick={() => requestCameraPreset("focus_start")}
            disabled={!startPoint}
            className="px-2 py-0.5 rounded text-emerald-300 hover:bg-[#182235] disabled:opacity-40"
            title="Focus Start Station"
          >
            Start
          </button>
          <button
            onClick={() => requestCameraPreset("focus_destination")}
            disabled={!destinationPoint}
            className="px-2 py-0.5 rounded text-rose-300 hover:bg-[#182235] disabled:opacity-40"
            title="Focus Destination"
          >
            Dest
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
            onClick={() => setShowRoute((v) => !v)}
            disabled={!activeRoute}
            className={`px-2 py-0.5 rounded transition-colors disabled:opacity-40 ${
              showRoute && activeRoute ? "bg-sky-500/20 text-sky-300" : "text-slate-400 hover:bg-[#182235]"
            }`}
            title="Toggle active route path visibility"
          >
            Path
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
          <button
            onClick={() => setShowTileBoundaries((v) => !v)}
            className={`px-2 py-0.5 rounded transition-colors ${
              showTileBoundaries ? "bg-amber-500/20 text-amber-300" : "text-slate-400 hover:bg-[#182235]"
            }`}
            title="Diagnostic Tile Boundaries (off by default)"
          >
            <Grid className="w-3 h-3 inline mr-1" />
            Tiles
          </button>
          <button
            onClick={() => requestCameraPreset("reset")}
            className="px-2 py-0.5 rounded text-slate-400 hover:text-slate-200 hover:bg-[#182235]"
            title="Reset Camera View"
          >
            <RefreshCw className="w-3 h-3 inline mr-1" />
            Reset
          </button>
          {corridorAssessment?.cache_validity && (
            <span
              className={`px-2 py-0.5 rounded font-mono text-[10px] border ${
                corridorAssessment.cache_validity === "CURRENT"
                  ? "border-emerald-700/70 bg-emerald-950/60 text-emerald-300"
                  : "border-amber-700/70 bg-amber-950/60 text-amber-300"
              }`}
              title={(corridorAssessment.stale_reasons ?? []).join(" | ") || "Evidence dependency checksum state"}
            >
              EVD:{corridorAssessment.cache_validity}
            </span>
          )}
        </div>
        </div>
      </div>

      {/* Overwrite Confirmation Prompt for Existing Start / Destination */}
      {pendingPickConfirm && (
        <div className="absolute top-16 left-1/2 -translate-x-1/2 z-30 flex items-center gap-3 bg-[#0e1525]/95 border border-amber-500/50 rounded-xl px-4 py-2 text-xs font-mono text-slate-200 shadow-2xl">
          <span>
            Replace existing{" "}
            <strong className={pendingPickConfirm.mode === "set_start" ? "text-emerald-300" : "text-rose-300"}>
              {pendingPickConfirm.mode === "set_start" ? "Start" : "Destination"}
            </strong>{" "}
            with {pendingPickConfirm.point.lat.toFixed(4)}°, {pendingPickConfirm.point.lon_east.toFixed(4)}°E (
            {pendingPickConfirm.point.elevation_m.toFixed(1)} m)?
          </span>
          <button
            onClick={() => {
              const p = pendingPickConfirm.point;
              if (pendingPickConfirm.mode === "set_start") {
                useRoutingStore.getState().setStartPoint({
                  lat: p.lat,
                  lon_east: p.lon_east,
                  label: `Start (${p.lat.toFixed(4)}°, ${p.lon_east.toFixed(4)}°)`,
                });
              } else {
                useRoutingStore.getState().setDestinationPoint({
                  lat: p.lat,
                  lon_east: p.lon_east,
                  label: `Dest (${p.lat.toFixed(4)}°, ${p.lon_east.toFixed(4)}°)`,
                });
              }
              useRoutingStore.getState().setSurfacePickMode("inspect");
              setPendingPickConfirm(null);
            }}
            className="px-2.5 py-1 rounded bg-amber-600 hover:bg-amber-500 text-white font-semibold"
          >
            Confirm
          </button>
          <button
            onClick={() => setPendingPickConfirm(null)}
            className="px-2 py-1 rounded border border-[#2d3b55] text-slate-300 hover:bg-[#161f32]"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Loading / Error State Overlay */}
      {(manifestLoading || tilesLoading) && (
        <div className="absolute top-14 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 bg-[#0d1424]/95 border border-cyan-500/40 rounded-full px-3 py-1 text-[11px] font-mono text-cyan-200 shadow-lg">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-cyan-400" />
          <span>
            {manifestLoading
              ? "Loading DEM 3D mesh manifest..."
              : `Streaming ${lodMode === "auto" ? "Auto " : ""}LOD ${activeLod} DEM tiles (${lodDescriptors.length})...`}
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

      {/* Bottom Live Telemetry, Route Summary & Context-Aware Legend */}
      <div className="absolute bottom-2.5 left-2.5 right-2.5 z-10 flex flex-wrap items-end justify-between gap-2 pointer-events-none">
        <div className="flex flex-col gap-1.5 items-start max-w-full">
          {activeRoute && (
            <div
              data-testid="viewport-route-summary"
              className={`flex flex-wrap items-center gap-2 backdrop-blur border rounded-lg px-2.5 py-1 text-[10px] font-mono pointer-events-auto ${
                staleRoute
                  ? "bg-amber-950/90 border-amber-500/50 text-amber-200"
                  : "bg-[#0b101b]/92 border-cyan-500/40 text-slate-200"
              }`}
            >
              <span className="font-semibold text-cyan-300">
                {activeRoute.mode_label}
              </span>
              <span>
                Horiz:{" "}
                <strong className={staleRoute ? "line-through opacity-60" : "text-white"}>
                  {activeRoute.total_horizontal_distance_m >= 1000
                    ? `${(activeRoute.total_horizontal_distance_m / 1000).toFixed(2)} km`
                    : `${activeRoute.total_horizontal_distance_m.toFixed(1)} m`}
                </strong>
              </span>
              <span>
                3D:{" "}
                <strong className={staleRoute ? "line-through opacity-60" : "text-white"}>
                  {activeRoute.total_surface_distance_m >= 1000
                    ? `${(activeRoute.total_surface_distance_m / 1000).toFixed(2)} km`
                    : `${activeRoute.total_surface_distance_m.toFixed(1)} m`}
                </strong>
              </span>
              <span>
                +{activeRoute.total_elevation_gain_m.toFixed(0)}m / -{activeRoute.total_elevation_loss_m.toFixed(0)}m
              </span>
              <span>Max {activeRoute.max_slope_deg.toFixed(1)}°</span>
              {staleRoute && (
                <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 font-semibold">
                  STALE ({staleReason || "Inputs changed"})
                </span>
              )}
            </div>
          )}

          <div
            ref={hoverHudRef}
            className="bg-[#0b101b]/92 backdrop-blur border border-[#243047] rounded-lg px-2.5 py-1 text-[11px] font-mono text-slate-200 pointer-events-auto"
          >
            Hover valid DEM surface for telemetry · Drag to orbit · Right-drag to pan · Wheel to zoom
          </div>
        </div>

        <div className="flex flex-col items-end gap-1.5">
          {/* Context-Aware Bottom-Right Terrain Legend */}
          {(() => {
            const effectiveOverlay =
              activeOverlayMode === "ortho" && !meshManifest?.ortho_dataset_id
                ? "elevation"
                : activeOverlayMode;
            const normSpec = meshManifest?.color_normalizations?.[effectiveOverlay];
            const stops = normSpec?.palette_stops || [];
            const gradientCss =
              stops.length >= 2
                ? `linear-gradient(to right, ${stops
                    .map((s) => `${s.color} ${(s.t * 100).toFixed(0)}%`)
                    .join(", ")})`
                : undefined;

            return (
              <div
                data-testid="terrain-overlay-legend"
                className="w-60 bg-[#0b101b]/94 backdrop-blur border border-[#243047] rounded-lg p-2 text-[10px] font-mono text-slate-300 pointer-events-auto shadow-lg space-y-1.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-slate-100">
                    {effectiveOverlay === "ortho"
                      ? "HiRISE Orthorectified"
                      : effectiveOverlay === "elevation"
                      ? "Elevation (m)"
                      : effectiveOverlay === "slope"
                      ? "Physical Slope (°)"
                      : "TRI Ruggedness (m)"}
                  </span>
                  <span className="text-[9px] text-slate-400">
                    {meshManifest?.native_resolution_m
                      ? `${meshManifest.native_resolution_m.toFixed(2)} m/px`
                      : "DEM"}
                  </span>
                </div>

                {effectiveOverlay === "ortho" ? (
                  <div className="text-[9px] text-slate-400 leading-relaxed">
                    <div>Product: {normSpec?.dataset_id || meshManifest?.ortho_dataset_id || meshManifest?.product_id}</div>
                    <div>Source reflectance only — RGB values are not physical elevation or slope measurements.</div>
                  </div>
                ) : (
                  <>
                    {gradientCss && (
                      <div
                        className="h-2.5 w-full rounded border border-slate-700/80"
                        style={{ background: gradientCss }}
                      />
                    )}
                    <div className="flex items-center justify-between text-[9px] text-slate-200">
                      <span>
                        {normSpec?.vmin != null ? normSpec.vmin.toFixed(effectiveOverlay === "roughness" ? 2 : 1) : "—"}
                        {effectiveOverlay === "slope" ? "°" : " m"}
                      </span>
                      {effectiveOverlay === "roughness" && (
                        <span className="text-slate-400">
                          r={normSpec?.physical_radius_m ?? 5.0}m
                        </span>
                      )}
                      <span>
                        {normSpec?.vmax != null ? normSpec.vmax.toFixed(effectiveOverlay === "roughness" ? 2 : 1) : "—"}
                        {effectiveOverlay === "slope" ? "°" : " m"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-[9px] text-slate-400">
                      <span>
                        {effectiveOverlay === "roughness"
                          ? "Lower local variation"
                          : effectiveOverlay === "elevation"
                          ? "MOLA Areoid"
                          : "True surface angle"}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <span className="inline-block w-2 h-2 rounded-sm border border-slate-500 bg-transparent" />
                        No-Data
                      </span>
                    </div>
                    {effectiveOverlay === "roughness" && (
                      <div className="text-[9px] text-slate-400">
                        Higher local variation at right · Window{" "}
                        {normSpec?.window_dimensions_m
                          ? `${normSpec.window_dimensions_m.width_m.toFixed(1)}×${normSpec.window_dimensions_m.height_m.toFixed(1)} m`
                          : "fixed metric"}
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          })()}

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
    </div>
  );
}
