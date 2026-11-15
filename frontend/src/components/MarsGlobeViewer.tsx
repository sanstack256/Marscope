"use client";

import { useEffect, useRef, useState } from "react";
import type * as CesiumTypes from "cesium";
import { API_BASE_URL } from "../lib/constants";
import { fetchHeightGridForCesium } from "../lib/terrainNoData";
import { useLayerStore } from "../stores/useLayerStore";
import { useAuthMissionStore } from "../stores/useAuthMissionStore";
import { useMissionStore } from "../stores/useMissionStore";
import { useRoutingStore } from "../stores/useRoutingStore";
import { Compass, Globe2, Layers, Minus, Plus, RotateCcw, Crosshair, Route as RouteIcon } from "lucide-react";
import { useSpatialStore } from "@/stores/useSpatialStore";
import type { GeoJsonGeometry } from "@/types";

function extractGlobeOuterRings(geom: GeoJsonGeometry | null | undefined): Array<Array<[number, number]>> {
  if (!geom || !geom.coordinates) return [];
  const toRing = (coords: unknown): Array<[number, number]> => {
    if (!Array.isArray(coords)) return [];
    const pts: Array<[number, number]> = [];
    for (const c of coords) {
      if (
        Array.isArray(c) &&
        c.length >= 2 &&
        typeof c[0] === "number" &&
        typeof c[1] === "number" &&
        Number.isFinite(c[0]) &&
        Number.isFinite(c[1])
      ) {
        const lon = c[0];
        const lat = Math.max(-89.9999, Math.min(89.9999, c[1]));
        const prev = pts[pts.length - 1];
        if (!prev || Math.abs(prev[0] - lon) > 1e-7 || Math.abs(prev[1] - lat) > 1e-7) {
          pts.push([lon, lat]);
        }
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

type SceneViewMode = "3D" | "2.5D" | "2D";
const GLOBAL_VIEW_CAMERA_HEIGHT_M = 9_000_000; // Initial UI framing distance; not a scientific parameter.

interface ManagedImageryLayer {
  cesiumLayer: CesiumTypes.ImageryLayer;
  endpoint: string;
}

// Bounding box covering local Gale Crater MOLA & HiRISE GeoTIFFs where real DEM terrain is served.
const GALE_DEM_REGION = {
  minLat: -6.0,
  maxLat: -4.0,
  minLonEast: 136.8,
  maxLonEast: 138.5,
};

function createMarscopeDemTerrainProvider(
  Cesium: typeof CesiumTypes,
  marsEllipsoid: CesiumTypes.Ellipsoid,
  signal: AbortSignal
): CesiumTypes.TerrainProvider {
  const baseProvider = new Cesium.EllipsoidTerrainProvider({ ellipsoid: marsEllipsoid });
  const tileCache = new Map<string, Promise<CesiumTypes.TerrainData>>();
  let pendingFetches = 0;

  const customProvider: CesiumTypes.TerrainProvider = {
    get errorEvent() {
      return baseProvider.errorEvent;
    },
    get credit() {
      return new Cesium.Credit("NASA HiRISE / MOLA Real DEM");
    },
    get tilingScheme() {
      return baseProvider.tilingScheme;
    },
    get hasWaterMask() {
      return false;
    },
    get hasVertexNormals() {
      return false;
    },
    get availability() {
      return undefined;
    },
    getLevelMaximumGeometricError(level: number) {
      return baseProvider.getLevelMaximumGeometricError(level);
    },
    getTileDataAvailable(x: number, y: number, level: number) {
      const rect = baseProvider.tilingScheme.tileXYToRectangle(x, y, level);
      const south = Cesium.Math.toDegrees(rect.south);
      const north = Cesium.Math.toDegrees(rect.north);
      let west = Cesium.Math.toDegrees(rect.west);
      let east = Cesium.Math.toDegrees(rect.east);
      if (west < 0) west += 360;
      if (east < 0) east += 360;
      const inGale =
        north >= GALE_DEM_REGION.minLat &&
        south <= GALE_DEM_REGION.maxLat &&
        east >= GALE_DEM_REGION.minLonEast &&
        west <= GALE_DEM_REGION.maxLonEast;
      return inGale ? level <= 15 : level <= 9;
    },
    loadTileDataAvailability() {
      return undefined;
    },
    requestTileGeometry(x: number, y: number, level: number) {
      const key = `${level}:${x}:${y}`;
      const cached = tileCache.get(key);
      if (cached) return cached;

      const rect = baseProvider.tilingScheme.tileXYToRectangle(x, y, level);
      const south = Cesium.Math.toDegrees(rect.south);
      const north = Cesium.Math.toDegrees(rect.north);
      let west = Cesium.Math.toDegrees(rect.west);
      let east = Cesium.Math.toDegrees(rect.east);
      if (west < 0) west += 360;
      if (east < 0) east += 360;

      const inGale =
        level >= 8 &&
        north >= GALE_DEM_REGION.minLat &&
        south <= GALE_DEM_REGION.maxLat &&
        east >= GALE_DEM_REGION.minLonEast &&
        west <= GALE_DEM_REGION.maxLonEast &&
        west < east &&
        south < north;

      if (!inGale) {
        return baseProvider.requestTileGeometry(x, y, level);
      }
      if (pendingFetches >= 6) {
        return undefined;
      }

      pendingFetches += 1;
      const gridSize = 33;
      const qs = new URLSearchParams({
        min_lat: south.toFixed(6),
        max_lat: north.toFixed(6),
        min_lon: west.toFixed(6),
        max_lon: east.toFixed(6),
        grid_size: String(gridSize),
      });

      const promise = fetchHeightGridForCesium(
        `${API_BASE_URL}/terrain/mesh/heightgrid?${qs.toString()}`,
        {
          signal,
          onSettled: () => {
            pendingFetches = Math.max(0, pendingFetches - 1);
          },
        }
      )
        .then(({ buffer, width, height }) => {
          return new Cesium.HeightmapTerrainData({
            buffer,
            width,
            height,
            childTileMask: level < 15 ? 15 : 0,
            structure: {
              heightScale: 1,
              heightOffset: 0,
              elementsPerHeight: 1,
              stride: 1,
            },
          });
        })
        .catch((err) => {
          // Never cache failed, aborted, unavailable, or partial-nodata terrain tiles
          tileCache.delete(key);
          throw err;
        });

      tileCache.set(key, promise);
      if (tileCache.size > 256) {
        const oldest = tileCache.keys().next().value;
        if (oldest !== undefined) tileCache.delete(oldest);
      }
      return promise;
    },
  };
  return customProvider;
}

export function MarsGlobeViewer() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<CesiumTypes.Viewer | null>(null);
  const cesiumRef = useRef<typeof CesiumTypes | null>(null);
  const ellipsoidRef = useRef<CesiumTypes.Ellipsoid | null>(null);
  const managedLayersRef = useRef<Record<string, ManagedImageryLayer>>({});
  const abortControllerRef = useRef<AbortController | null>(null);
  const lastReportedRenderedRef = useRef<Record<string, boolean>>({});
  const reportedErrorRef = useRef<Record<string, string>>({});

  const [viewerReady, setViewerReady] = useState(false);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<SceneViewMode>("3D");
  const [cursorCoords, setCursorCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [cameraTelemetry, setCameraTelemetry] = useState<{
    altitudeKm: number;
    headingDeg: number;
    scaleLabel: string;
  }>({ altitudeKm: 0, headingDeg: 0, scaleLabel: "unavailable" });

  const availableLayers = useLayerStore((s) => s.availableLayers);
  const layerStates = useLayerStore((s) => s.layerStates);
  const layerOrder = useLayerStore((s) => s.layerOrder);

  const selectedDestination = useMissionStore((s) => s.selectedDestination);
  const localizationStatus = useMissionStore((s) => s.localizationStatus);
  const compositionCandidates = useMissionStore((s) => s.compositionCandidates);
  const selectedCandidateId = useMissionStore((s) => s.selectedCandidateId);
  const evaluateDestination = useMissionStore((s) => s.evaluateDestination);

  const activeRoute = useRoutingStore((s) => s.activeRoute);
  const startPoint = useRoutingStore((s) => s.startPoint);
  const destinationPoint = useRoutingStore((s) => s.destinationPoint);
  const selectedWaypointSeq = useRoutingStore((s) => s.selectedWaypointSeq);

  // Initialize CesiumJS Mars Globe once
  useEffect(() => {
    let destroyed = false;
    let handler: CesiumTypes.ScreenSpaceEventHandler | null = null;
    let removeCameraListener: (() => void) | null = null;
    const terrainAbortController = new AbortController();

    async function initCesium() {
      if (!containerRef.current) return;
      try {
        (window as unknown as { CESIUM_BASE_URL?: string }).CESIUM_BASE_URL = "/cesium/";

        // Inject Cesium widget stylesheet once
        if (!document.getElementById("cesium-widgets-css")) {
          const link = document.createElement("link");
          link.id = "cesium-widgets-css";
          link.rel = "stylesheet";
          link.href = "/cesium/Widgets/widgets.css";
          document.head.appendChild(link);
        }

        const Cesium = await import("cesium");
        if (destroyed || !containerRef.current) return;

        (Cesium.buildModuleUrl as unknown as { setBaseUrl?: (url: string) => void }).setBaseUrl?.("/cesium/");
        cesiumRef.current = Cesium;

        // Authoritative IAU 2000 Mars Ellipsoid (a = 3396.19 km, c = 3376.20 km)
        const marsEllipsoid = new Cesium.Ellipsoid(3396190.0, 3396190.0, 3376200.0);
        ellipsoidRef.current = marsEllipsoid;

        const demTerrainProvider = createMarscopeDemTerrainProvider(
          Cesium,
          marsEllipsoid,
          terrainAbortController.signal
        );

        const viewer = new Cesium.Viewer(containerRef.current, {
          globe: new Cesium.Globe(marsEllipsoid),
          baseLayer: false,
          terrainProvider: demTerrainProvider,
          geocoder: false,
          homeButton: false,
          sceneModePicker: false,
          baseLayerPicker: false,
          navigationHelpButton: false,
          animation: false,
          timeline: false,
          fullscreenButton: false,
          infoBox: false,
          selectionIndicator: false,
          skyAtmosphere: false,
          creditContainer: document.createElement("div"),
          requestRenderMode: true,
          maximumRenderTimeChange: Number.POSITIVE_INFINITY,
        });

        viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#0b0d13");
        viewer.scene.globe.showGroundAtmosphere = false;
        viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#06080d");
        viewer.scene.sun = new Cesium.Sun();
        viewer.scene.globe.enableLighting = false;

        // Start at a global view; the study area comes from explicit user selection.
        viewer.camera.setView({
          destination: marsEllipsoid.cartographicToCartesian(
            Cesium.Cartographic.fromDegrees(0, 0, GLOBAL_VIEW_CAMERA_HEIGHT_M)
          ),
          orientation: {
            heading: 0.0,
            pitch: -Cesium.Math.PI_OVER_TWO,
            roll: 0.0,
          },
        });

        // Keep high-frequency camera events off React. Telemetry is sampled at a
        // controlled cadence and once at the end of each camera gesture.
        let telemetryTimer: ReturnType<typeof setTimeout> | null = null;
        const updateTelemetry = () => {
          if (!viewer || viewer.isDestroyed()) return;
          const headingRadians = viewer.camera.heading;
          // Cesium can briefly expose an undefined heading while the camera is
          // initializing or changing scene modes. Skip this telemetry sample;
          // the next camera event will retry once the orientation is available.
          if (!Number.isFinite(headingRadians)) return;

          const carto = marsEllipsoid.cartesianToCartographic(viewer.camera.position);
          const altKm = carto ? Math.max(0.05, carto.height / 1000.0) : 0;
          const headingDeg = ((Cesium.Math.toDegrees(headingRadians) % 360) + 360) % 360;
          const centerRay = viewer.camera.getPickRay(new Cesium.Cartesian2(
            viewer.scene.canvas.clientWidth / 2,
            viewer.scene.canvas.clientHeight / 2,
          ));
          const centerHit = centerRay ? viewer.scene.globe.pick(centerRay, viewer.scene) : undefined;
          const edgeRay = viewer.camera.getPickRay(new Cesium.Cartesian2(
            Math.min(viewer.scene.canvas.clientWidth - 1, viewer.scene.canvas.clientWidth / 2 + 40),
            viewer.scene.canvas.clientHeight / 2,
          ));
          const edgeHit = edgeRay ? viewer.scene.globe.pick(edgeRay, viewer.scene) : undefined;
          const scaleKm = centerHit && edgeHit
            ? Cesium.Cartesian3.distance(centerHit, edgeHit) / 1000
            : null;
          const scaleLabel = scaleKm == null
            ? "unavailable"
            : scaleKm >= 1 ? `${scaleKm >= 100 ? Math.round(scaleKm) : scaleKm.toFixed(1)} km` : `${Math.round(scaleKm * 1000)} m`;
          setCameraTelemetry((current) => {
            if (Math.abs(current.altitudeKm - altKm) < 0.05 && Math.abs(current.headingDeg - headingDeg) < 0.5 && current.scaleLabel === scaleLabel) return current;
            return { altitudeKm: altKm, headingDeg, scaleLabel };
          });
        };
        const scheduleTelemetry = () => {
          if (telemetryTimer) return;
          telemetryTimer = setTimeout(() => {
            telemetryTimer = null;
            updateTelemetry();
          }, 250);
        };
        viewer.camera.changed.addEventListener(scheduleTelemetry);
        viewer.camera.moveEnd.addEventListener(updateTelemetry);
        const initialScaleMeasurement = () => {
          updateTelemetry();
          viewer.scene.postRender.removeEventListener(initialScaleMeasurement);
        };
        viewer.scene.postRender.addEventListener(initialScaleMeasurement);
        removeCameraListener = () => {
          viewer.camera.changed.removeEventListener(scheduleTelemetry);
          viewer.camera.moveEnd.removeEventListener(updateTelemetry);
          viewer.scene.postRender.removeEventListener(initialScaleMeasurement);
          if (telemetryTimer) clearTimeout(telemetryTimer);
        };
        updateTelemetry();

        // Pointer interaction handlers: hover coordinates + click destination inspection
        handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
        handler.setInputAction((movement: CesiumTypes.ScreenSpaceEventHandler.MotionEvent) => {
          const pos = viewer.camera.pickEllipsoid(movement.endPosition, marsEllipsoid);
          if (pos) {
            const carto = marsEllipsoid.cartesianToCartographic(pos);
            setCursorCoords({
              lat: Cesium.Math.toDegrees(carto.latitude),
              lon: Cesium.Math.toDegrees(carto.longitude),
            });
          } else {
            setCursorCoords(null);
          }
        }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

        handler.setInputAction((click: CesiumTypes.ScreenSpaceEventHandler.PositionedEvent) => {
          const picked = viewer.scene.pick(click.position);
          const pickedEntityId =
            picked && typeof picked === "object" && "id" in picked && picked.id && typeof picked.id === "object" && "id" in picked.id
              ? String((picked.id as { id: unknown }).id)
              : null;

          if (pickedEntityId && pickedEntityId.startsWith("footprint:")) {
            const did = pickedEntityId.slice("footprint:".length);
            const fp = useSpatialStore
              .getState()
              .intersectingFootprints.find((f) => f.dataset_id === did);
            if (fp) {
              useSpatialStore.getState().setSelectedEntity({ kind: "footprint", data: fp });
              return;
            }
          }

          if (pickedEntityId && pickedEntityId.startsWith("gap:")) {
            const gid = pickedEntityId.slice("gap:".length);
            const gap = useSpatialStore
              .getState()
              .coverageReport?.evidence_gaps.find((g) => g.gap_id === gid);
            if (gap) {
              useSpatialStore.getState().setSelectedEntity({ kind: "gap", data: gap });
              return;
            }
          }

          if (pickedEntityId && pickedEntityId.startsWith("waypoint:")) {
            const seq = Number(pickedEntityId.slice("waypoint:".length));
            if (Number.isFinite(seq)) {
              useRoutingStore.getState().selectWaypoint(seq, false);
              return;
            }
          }

          if (pickedEntityId && pickedEntityId.startsWith("candidate:")) {
            const candidateId = pickedEntityId.slice("candidate:".length);
            const storeState = useMissionStore.getState();
            storeState.selectCompositionCandidate(candidateId);
            const matched = storeState.compositionCandidates.find((c) => c.candidate_id === candidateId);
            if (matched) {
              if (abortControllerRef.current) abortControllerRef.current.abort();
              const controller = new AbortController();
              abortControllerRef.current = controller;
              evaluateDestination(matched.latitude, matched.longitude_east, matched.cluster_label, controller.signal);
              return;
            }
          }

          const pos = viewer.camera.pickEllipsoid(click.position, marsEllipsoid);
          if (!pos) return;
          const carto = marsEllipsoid.cartesianToCartographic(pos);
          const lat = Number(Cesium.Math.toDegrees(carto.latitude).toFixed(6));
          const lon = Number(Cesium.Math.toDegrees(carto.longitude).toFixed(6));

          if (abortControllerRef.current) {
            abortControllerRef.current.abort();
          }
          const controller = new AbortController();
          abortControllerRef.current = controller;
          evaluateDestination(lat, lon, undefined, controller.signal);
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

        const scc = viewer.scene.screenSpaceCameraController;
        scc.minimumZoomDistance = 5;
        scc.minimumCollisionTerrainHeight = 5;
        scc.maximumZoomDistance = 25000000;
        scc.inertiaSpin = 0.45;
        scc.inertiaTranslate = 0.45;
        scc.inertiaZoom = 0.35;
        scc.zoomFactor = 5.0;
        scc.enableCollisionDetection = true;
        scc.enableTilt = true;
        scc.enableLook = true;
        viewer.scene.requestRender();

        viewerRef.current = viewer;
        setViewerReady(true);
      } catch (err) {
        setViewerError(err instanceof Error ? err.message : "Failed to initialize Mars 3D WebGL engine.");
      }
    }

    initCesium();

    return () => {
      destroyed = true;
      terrainAbortController.abort();
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      if (removeCameraListener) removeCameraListener();
      if (handler && !handler.isDestroyed()) handler.destroy();
      if (viewerRef.current && !viewerRef.current.isDestroyed()) {
        viewerRef.current.destroy();
      }
      viewerRef.current = null;
      managedLayersRef.current = {};
    };
  }, [evaluateDestination]);

  // Sync dynamic backend imagery layers to Cesium Viewer
  useEffect(() => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    const marsEllipsoid = ellipsoidRef.current;
    if (!viewerReady || !viewer || viewer.isDestroyed() || !Cesium || !marsEllipsoid) return;

    const imageryCollection = viewer.imageryLayers;
    const activeIds = new Set(availableLayers.map((l) => l.layer_id));

    // Remove stale layers no longer in catalog
    Object.keys(managedLayersRef.current).forEach((lid) => {
      if (!activeIds.has(lid)) {
        imageryCollection.remove(managedLayersRef.current[lid].cesiumLayer, true);
        delete managedLayersRef.current[lid];
      }
    });

    // Ensure providers exist & sync ordering bottom-to-top (reverse of UI list order)
    const orderedIds = [...layerOrder].reverse();
    const tilingScheme = new Cesium.GeographicTilingScheme({ ellipsoid: marsEllipsoid });

    orderedIds.forEach((lid) => {
      const layer = availableLayers.find((l) => l.layer_id === lid);
      const state = layerStates[lid];
      if (!layer || !layer.rendering_endpoint || !state) return;

      let managed = managedLayersRef.current[lid];
      if (!managed || managed.endpoint !== layer.rendering_endpoint) {
        if (managed) {
          imageryCollection.remove(managed.cesiumLayer, true);
        }

        // Handle bounding rectangle if constrained regional raster
        let rectangle = Cesium.Rectangle.MAX_VALUE;
        if (layer.spatial_bounds && layer.spatial_bounds.length === 4) {
          const [minLon, minLat, maxLon, maxLat] = layer.spatial_bounds;
          if (maxLon - minLon < 359.0 || maxLat - minLat < 179.0) {
            const clampedMinLon = Math.max(-180, minLon > 180 ? minLon - 360 : minLon);
            const clampedMaxLon = Math.min(180, maxLon > 180 ? maxLon - 360 : maxLon);
            if (clampedMaxLon > clampedMinLon) {
              rectangle = Cesium.Rectangle.fromDegrees(clampedMinLon, minLat, clampedMaxLon, maxLat);
            }
          }
        }

        const provider = new Cesium.UrlTemplateImageryProvider({
          url: layer.rendering_endpoint,
          tilingScheme,
          rectangle,
          maximumLevel: layer.maximum_zoom ?? 7,
          tileWidth: 256,
          tileHeight: 256,
          credit: layer.attribution,
        });

        provider.errorEvent.addEventListener((tileErr) => {
          const msg = tileErr?.message || "Tile load failed";
          if (reportedErrorRef.current[lid] === msg) return;
          reportedErrorRef.current[lid] = msg;
          queueMicrotask(() => {
            useLayerStore.getState().recordTileError(lid, msg);
          });
        });

        const cesiumLayer = imageryCollection.addImageryProvider(provider);
        managed = { cesiumLayer, endpoint: layer.rendering_endpoint };
        managedLayersRef.current[lid] = managed;
        if (reportedErrorRef.current[lid]) {
          delete reportedErrorRef.current[lid];
          queueMicrotask(() => {
            useLayerStore.getState().clearTileErrors(lid);
          });
        }
      }

      managed.cesiumLayer.show = state.visible;
      managed.cesiumLayer.alpha = state.opacity;
      if (lastReportedRenderedRef.current[lid] !== state.visible) {
        lastReportedRenderedRef.current[lid] = state.visible;
        const visibleSnap = state.visible;
        queueMicrotask(() => {
          useLayerStore.getState().markLayerRendered(lid, visibleSnap);
        });
      }
    });

    // Apply exact z-index stack order in Cesium ImageryLayerCollection
    orderedIds.forEach((lid) => {
      const managed = managedLayersRef.current[lid];
      if (managed && imageryCollection.contains(managed.cesiumLayer)) {
        imageryCollection.raiseToTop(managed.cesiumLayer);
      }
    });
    viewer.scene.requestRender();
  }, [viewerReady, availableLayers, layerStates, layerOrder]);

  // Sync Destination, Manual Localization & Composition Candidate Markers on Globe
  useEffect(() => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    const marsEllipsoid = ellipsoidRef.current;
    if (!viewerReady || !viewer || viewer.isDestroyed() || !Cesium || !marsEllipsoid) return;

    let markerSource = viewer.dataSources.getByName("marscope-markers")[0];
    if (!markerSource) {
      markerSource = new Cesium.CustomDataSource("marscope-markers");
      void viewer.dataSources.add(markerSource);
    }
    const entities = markerSource.entities;
    const desired = new Set<string>();

    // Render Composition Discovery candidate markers
    compositionCandidates.forEach((cand, idx) => {
      if (cand.location_semantic_type === "unlocated") return;
      const id = `candidate:${cand.candidate_id}`;
      desired.add(id);
      const isSelected = cand.candidate_id === selectedCandidateId;
      const isRoverStation = cand.location_semantic_type === "rover_station_location";
      const lon180 = cand.longitude_east > 180 ? cand.longitude_east - 360 : cand.longitude_east;
      const pos = marsEllipsoid.cartographicToCartesian(
        Cesium.Cartographic.fromDegrees(lon180, cand.latitude, 0)
      );
      const valStr =
        cand.best_normalized_value != null
          ? `${cand.best_normalized_value.toFixed(2)} ${cand.best_normalized_unit ?? ""}`.trim()
          : cand.best_species_id;
      const semanticTag = isRoverStation ? "Station" : "Target";
      const baseColor = isRoverStation ? "#c084fc" : "#f59e0b";
      const entity = entities.getById(id) ?? entities.add({ id });
      Object.assign(entity, {
        position: pos,
        point: {
          pixelSize: isSelected ? 14 : isRoverStation ? 9 : 11,
          color: Cesium.Color.fromCssColorString(isSelected ? "#34d399" : baseColor),
          outlineColor: isSelected ? Cesium.Color.WHITE : Cesium.Color.fromCssColorString("#0b0d13"),
          outlineWidth: isSelected ? 2.5 : 1.5,
        },
        label: isSelected || idx < 5
          ? {
              text: `#${idx + 1} [${semanticTag}] ${cand.cluster_label} (${valStr})`,
              font: isSelected ? "11px monospace" : "10px monospace",
              fillColor: Cesium.Color.fromCssColorString(
                isSelected ? "#a7f3d0" : isRoverStation ? "#e9d5ff" : "#fde68a"
              ),
              backgroundColor: Cesium.Color.fromCssColorString("#0b0d13D9"),
              showBackground: true,
              pixelOffset: new Cesium.Cartesian2(0, -18),
            }
          : undefined,
      });
    });

    if (selectedDestination) {
      const pos = marsEllipsoid.cartographicToCartesian(
        Cesium.Cartographic.fromDegrees(selectedDestination.normalized_longitude_180, selectedDestination.latitude, 0)
      );
      const entity = entities.getById("selected-destination") ?? entities.add({ id: "selected-destination" });
      desired.add("selected-destination");
      Object.assign(entity, {
        position: pos,
        point: {
          pixelSize: 12,
          color: Cesium.Color.fromCssColorString("#e25b38"),
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 2,
        },
        label: {
          text: `TARGET (${selectedDestination.latitude.toFixed(3)}°, ${selectedDestination.longitude.toFixed(3)}°)`,
          font: "11px monospace",
          fillColor: Cesium.Color.WHITE,
          backgroundColor: Cesium.Color.fromCssColorString("#0b0d13CC"),
          showBackground: true,
          pixelOffset: new Cesium.Cartesian2(0, -20),
        },
      });
    }

    const activePos = localizationStatus?.current_position;
    if (activePos && activePos.latitude != null && activePos.longitude != null) {
      const pos = marsEllipsoid.cartographicToCartesian(
        Cesium.Cartographic.fromDegrees(activePos.longitude, activePos.latitude, 0)
      );
      const entity = entities.getById("explorer-position") ?? entities.add({ id: "explorer-position" });
      desired.add("explorer-position");
      Object.assign(entity, {
        position: pos,
        point: {
          pixelSize: 11,
          color: Cesium.Color.fromCssColorString("#38bdf8"),
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 2,
        },
        label: {
          text: `POS (${activePos.latitude.toFixed(3)}°, ${activePos.longitude.toFixed(3)}°)`,
          font: "11px monospace",
          fillColor: Cesium.Color.fromCssColorString("#bae6fd"),
          backgroundColor: Cesium.Color.fromCssColorString("#0b0d13CC"),
          showBackground: true,
          pixelOffset: new Cesium.Cartesian2(0, 20),
        },
      });
    }

    for (let i = entities.values.length - 1; i >= 0; i -= 1) {
      const entity = entities.values[i];
      if (!desired.has(entity.id)) entities.remove(entity);
    }
    viewer.scene.requestRender();
  }, [viewerReady, selectedDestination, localizationStatus, compositionCandidates, selectedCandidateId]);

  // Smoothly fly camera toward newly selected composition candidate
  useEffect(() => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    const marsEllipsoid = ellipsoidRef.current;
    if (!viewerReady || !viewer || viewer.isDestroyed() || !Cesium || !marsEllipsoid || !selectedCandidateId) {
      return;
    }
    const cand = compositionCandidates.find((c) => c.candidate_id === selectedCandidateId);
    if (!cand) return;
    const lon180 = cand.longitude_east > 180 ? cand.longitude_east - 360 : cand.longitude_east;
    const camCarto = marsEllipsoid.cartesianToCartographic(viewer.camera.position);
    const targetH = camCarto?.height ?? GLOBAL_VIEW_CAMERA_HEIGHT_M;
      viewer.camera.flyTo({
      destination: marsEllipsoid.cartographicToCartesian(
        Cesium.Cartographic.fromDegrees(lon180, cand.latitude, targetH)
      ),
      orientation: { heading: 0.0, pitch: -Cesium.Math.PI_OVER_TWO, roll: 0.0 },
      duration: 0.9,
      complete: () => viewer.scene.requestRender(),
    });
  }, [viewerReady, selectedCandidateId, compositionCandidates]);

  // Sync Active Route, Waypoints, Start/Destination markers on Cesium Mars Globe
  useEffect(() => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    const marsEllipsoid = ellipsoidRef.current;
    if (!viewerReady || !viewer || viewer.isDestroyed() || !Cesium || !marsEllipsoid) return;

    let routeSource = viewer.dataSources.getByName("marscope-route")[0];
    if (!routeSource) {
      routeSource = new Cesium.CustomDataSource("marscope-route");
      void viewer.dataSources.add(routeSource);
    }
    const entities = routeSource.entities;
    entities.removeAll();

    const toLon180 = (lonEast: number) => (lonEast > 180 ? lonEast - 360 : lonEast);

    if (startPoint) {
      entities.add({
        id: "route-start",
        position: marsEllipsoid.cartographicToCartesian(
          Cesium.Cartographic.fromDegrees(toLon180(startPoint.lon_east), startPoint.lat, 0)
        ),
        point: {
          pixelSize: 12,
          color: Cesium.Color.fromCssColorString("#10b981"),
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 2,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        },
        label: {
          text: `START: ${startPoint.label || "Origin"}`,
          font: "10px monospace",
          fillColor: Cesium.Color.fromCssColorString("#a7f3d0"),
          backgroundColor: Cesium.Color.fromCssColorString("#0b0d13D9"),
          showBackground: true,
          pixelOffset: new Cesium.Cartesian2(0, -18),
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        },
      });
    }

    if (destinationPoint) {
      entities.add({
        id: "route-destination",
        position: marsEllipsoid.cartographicToCartesian(
          Cesium.Cartographic.fromDegrees(toLon180(destinationPoint.lon_east), destinationPoint.lat, 0)
        ),
        point: {
          pixelSize: 12,
          color: Cesium.Color.fromCssColorString("#f43f5e"),
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 2,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        },
        label: {
          text: `DEST: ${destinationPoint.label || "Objective"}`,
          font: "10px monospace",
          fillColor: Cesium.Color.fromCssColorString("#fecdd3"),
          backgroundColor: Cesium.Color.fromCssColorString("#0b0d13D9"),
          showBackground: true,
          pixelOffset: new Cesium.Cartesian2(0, -18),
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        },
      });
    }

    if (activeRoute && activeRoute.vertices.length >= 2) {
      const returnLegStartSeq =
        activeRoute.legs.find((l) => l.is_return_leg)?.vertex_start_seq ?? Number.POSITIVE_INFINITY;

      const outboundPositions = activeRoute.vertices
        .filter((v) => v.seq <= returnLegStartSeq)
        .map((v) =>
          marsEllipsoid.cartographicToCartesian(
            Cesium.Cartographic.fromDegrees(toLon180(v.lon_east), v.lat, 0)
          )
        );
      if (outboundPositions.length >= 2) {
        entities.add({
          id: "route-polyline-outbound",
          polyline: {
            positions: outboundPositions,
            width: 3.5,
            clampToGround: true,
            material: Cesium.Color.fromCssColorString("#38bdf8"),
          },
        });
      }

      const returnPositions = activeRoute.vertices
        .filter((v) => v.seq >= returnLegStartSeq)
        .map((v) =>
          marsEllipsoid.cartographicToCartesian(
            Cesium.Cartographic.fromDegrees(toLon180(v.lon_east), v.lat, 0)
          )
        );
      if (returnPositions.length >= 2) {
        entities.add({
          id: "route-polyline-return",
          polyline: {
            positions: returnPositions,
            width: 3,
            clampToGround: true,
            material: new Cesium.PolylineDashMaterialProperty({
              color: Cesium.Color.fromCssColorString("#fb923c"),
            }),
          },
        });
      }

      activeRoute.vertices
        .filter((v) => v.is_stop || selectedWaypointSeq === v.seq)
        .forEach((v) => {
          const isSelected = selectedWaypointSeq === v.seq;
          entities.add({
            id: `waypoint:${v.seq}`,
            position: marsEllipsoid.cartographicToCartesian(
              Cesium.Cartographic.fromDegrees(toLon180(v.lon_east), v.lat, 0)
            ),
            point: {
              pixelSize: isSelected ? 13 : 9,
              color: Cesium.Color.fromCssColorString(isSelected ? "#fde047" : "#38bdf8"),
              outlineColor: Cesium.Color.fromCssColorString("#0b0d13"),
              outlineWidth: isSelected ? 2.5 : 1.5,
              heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            },
          });
        });
    }

    viewer.scene.requestRender();
  }, [viewerReady, activeRoute, startPoint, destinationPoint, selectedWaypointSeq]);

  // Sync Prompt 19 Swath Footprints & Evidence-Gap Overlays on Mars Globe
  const intersectingFootprints = useSpatialStore((s) => s.intersectingFootprints);
  const coverageReport = useSpatialStore((s) => s.coverageReport);
  const showFootprintsOverlay = useSpatialStore((s) => s.showFootprintsOverlay);
  const showGapsOverlay = useSpatialStore((s) => s.showGapsOverlay);
  const showLandingSiteOverlay = useSpatialStore((s) => s.showLandingSiteOverlay);
  const showCrewOverlay = useSpatialStore((s) => s.showCrewOverlay);
  const showFieldObservationsOverlay = useSpatialStore((s) => s.showFieldObservationsOverlay);
  const focusCoordinate = useSpatialStore((s) => s.focusCoordinate);

  const landingSiteBundle = useAuthMissionStore((s) => s.landingSiteBundle);
  const crewPositions = useAuthMissionStore((s) => s.positions);
  const sosEvents = useAuthMissionStore((s) => s.sosEvents);
  const fieldObservations = useAuthMissionStore((s) => s.observations);

  useEffect(() => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    const marsEllipsoid = ellipsoidRef.current;
    if (!viewerReady || !viewer || viewer.isDestroyed() || !Cesium || !marsEllipsoid || !focusCoordinate) return;
    const lon180 = focusCoordinate.lon > 180 ? focusCoordinate.lon - 360 : focusCoordinate.lon;
    viewer.camera.flyTo({
      destination: marsEllipsoid.cartographicToCartesian(
        Cesium.Cartographic.fromDegrees(lon180, focusCoordinate.lat, focusCoordinate.heightM ?? 6500)
      ),
      orientation: { heading: 0, pitch: Cesium.Math.toRadians(-48), roll: 0 },
      duration: 0.9,
      complete: () => viewer.scene.requestRender(),
    });
  }, [viewerReady, focusCoordinate]);

  useEffect(() => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    const marsEllipsoid = ellipsoidRef.current;
    if (!viewerReady || !viewer || viewer.isDestroyed() || !Cesium || !marsEllipsoid) return;

    let spatialSource = viewer.dataSources.getByName("marscope-spatial-overlays")[0];
    if (!spatialSource) {
      spatialSource = new Cesium.CustomDataSource("marscope-spatial-overlays");
      void viewer.dataSources.add(spatialSource);
    }
    const entities = spatialSource.entities;
    entities.removeAll();
    const toLon180 = (lonEast: number) => (lonEast > 180 ? lonEast - 360 : lonEast);
    const isFiniteCoord = (lon: unknown, lat: unknown, h: unknown = 0): boolean =>
      typeof lon === "number" &&
      Number.isFinite(lon) &&
      typeof lat === "number" &&
      Number.isFinite(lat) &&
      typeof h === "number" &&
      Number.isFinite(h);

    if (
      showLandingSiteOverlay &&
      landingSiteBundle?.landing_site &&
      isFiniteCoord(
        landingSiteBundle.landing_site.longitude_east,
        landingSiteBundle.landing_site.latitude,
        landingSiteBundle.landing_site.elevation_m ?? 0
      )
    ) {
      const ls = landingSiteBundle.landing_site;
      entities.add({
        id: `mission:landing-site:${ls.landing_site_id}`,
        name: `Landing Site: ${ls.name}`,
        position: marsEllipsoid.cartographicToCartesian(
          Cesium.Cartographic.fromDegrees(toLon180(ls.longitude_east), ls.latitude, (ls.elevation_m ?? 0) + 120)
        ),
        point: {
          pixelSize: 13,
          color: Cesium.Color.fromCssColorString("#1F9D68"),
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 2,
        },
        label: {
          text: `LANDING SITE: ${ls.name}`,
          font: "11px monospace",
          fillColor: Cesium.Color.fromCssColorString("#4ade80"),
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          pixelOffset: new Cesium.Cartesian2(0, -18),
        },
      });

      const perimGeom = landingSiteBundle.perimeter?.geometry_geojson as
        | { geometry?: GeoJsonGeometry }
        | GeoJsonGeometry
        | null
        | undefined;
      const geomObj =
        perimGeom && "geometry" in perimGeom && perimGeom.geometry ? perimGeom.geometry : (perimGeom as GeoJsonGeometry | null);
      if (geomObj) {
        const rings = extractGlobeOuterRings(geomObj);
        rings.forEach((ring, rIdx) => {
          const flat = ring.flatMap(([lon, lat]) => [toLon180(lon), lat]);
          if (flat.length < 6) return;
          entities.add({
            id: `mission:perimeter:${rIdx}`,
            polygon: {
              hierarchy: Cesium.Cartesian3.fromDegreesArray(flat, marsEllipsoid),
              material: Cesium.Color.fromCssColorString("#22B8CF").withAlpha(0.18),
              outline: true,
              outlineColor: Cesium.Color.fromCssColorString("#22B8CF"),
              height: 20,
            },
          });
        });
      }
    }

    if (showCrewOverlay && crewPositions.length > 0) {
      crewPositions.forEach((cp) => {
        if (!isFiniteCoord(cp.longitude_east, cp.latitude, cp.elevation_m ?? 0)) return;
        entities.add({
          id: `mission:crew:${cp.astronaut_id}`,
          name: cp.display_name || cp.astronaut_id,
          position: marsEllipsoid.cartographicToCartesian(
            Cesium.Cartographic.fromDegrees(toLon180(cp.longitude_east), cp.latitude, (cp.elevation_m ?? 0) + 80)
          ),
          point: {
            pixelSize: 11,
            color: Cesium.Color.fromCssColorString(cp.is_stale ? "#D98A1F" : "#22B8CF"),
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 2,
          },
          label: {
            text: `${cp.display_name || "Crew"}${cp.is_stale ? " (STALE)" : ""}`,
            font: "10px monospace",
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            pixelOffset: new Cesium.Cartesian2(0, -16),
          },
        });
      });
    }

    if (showFieldObservationsOverlay && fieldObservations.length > 0) {
      fieldObservations.slice(0, 40).forEach((obs) => {
        if (!isFiniteCoord(obs.longitude_east, obs.latitude, obs.elevation_m ?? 0)) return;
        entities.add({
          id: `mission:obs:${obs.observation_id}`,
          name: `${obs.category}: ${obs.species_display_name || obs.description}`,
          position: marsEllipsoid.cartographicToCartesian(
            Cesium.Cartographic.fromDegrees(toLon180(obs.longitude_east!), obs.latitude!, (obs.elevation_m ?? 0) + 60)
          ),
          point: {
            pixelSize: 9,
            color: Cesium.Color.fromCssColorString("#E25B38"),
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 1.5,
          },
        });
      });
    }

    sosEvents
      .filter((s) => s.status !== "RESOLVED" && s.status !== "CANCELLED" && isFiniteCoord(s.longitude_east, s.latitude, s.elevation_m ?? 0))
      .forEach((sos) => {
        entities.add({
          id: `mission:sos:${sos.sos_id}`,
          name: `SOS: ${sos.astronaut_display_name}`,
          position: marsEllipsoid.cartographicToCartesian(
            Cesium.Cartographic.fromDegrees(toLon180(sos.longitude_east!), sos.latitude!, (sos.elevation_m ?? 0) + 140)
          ),
          point: {
            pixelSize: 15,
            color: Cesium.Color.fromCssColorString("#DC3545"),
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 2.5,
          },
          label: {
            text: `SOS: ${sos.astronaut_display_name}`,
            font: "bold 11px monospace",
            fillColor: Cesium.Color.fromCssColorString("#ff6b7a"),
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            pixelOffset: new Cesium.Cartesian2(0, -20),
          },
        });
      });

    if (showFootprintsOverlay && intersectingFootprints.length > 0) {
      intersectingFootprints.slice(0, 12).forEach((fp) => {
        const rings = extractGlobeOuterRings(fp.valid_data_geojson || fp.footprint_geojson);
        rings.forEach((ring, rIdx) => {
          const flat = ring.flatMap(([lon, lat]) => [toLon180(lon), lat]);
          if (flat.length < 6) return;
          const isApprox = fp.is_approximate;
          entities.add({
            id: rIdx === 0 ? `footprint:${fp.dataset_id}` : `footprint:${fp.dataset_id}:${rIdx}`,
            polygon: {
              hierarchy: Cesium.Cartesian3.fromDegreesArray(flat, marsEllipsoid),
              material: Cesium.Color.fromCssColorString(isApprox ? "#64748b" : "#22d3ee").withAlpha(0.08),
              outline: true,
              outlineColor: Cesium.Color.fromCssColorString(isApprox ? "#94a3b8" : "#22d3ee"),
              height: 10,
            },
          });
        });
      });
    }

    if (showGapsOverlay && coverageReport?.evidence_gaps?.length) {
      coverageReport.evidence_gaps.slice(0, 12).forEach((gap) => {
        const rings = extractGlobeOuterRings(gap.geometry_geojson);
        rings.forEach((ring, rIdx) => {
          const flat = ring.flatMap(([lon, lat]) => [toLon180(lon), lat]);
          if (flat.length < 6) return;
          entities.add({
            id: rIdx === 0 ? `gap:${gap.gap_id}` : `gap:${gap.gap_id}:${rIdx}`,
            polygon: {
              hierarchy: Cesium.Cartesian3.fromDegreesArray(flat, marsEllipsoid),
              material: Cesium.Color.fromCssColorString("#f59e0b").withAlpha(0.14),
              outline: true,
              outlineColor: Cesium.Color.fromCssColorString("#fb7185"),
              height: 15,
            },
          });
        });
      });
    }

    viewer.scene.requestRender();
  }, [
    viewerReady,
    intersectingFootprints,
    coverageReport,
    showFootprintsOverlay,
    showGapsOverlay,
    showLandingSiteOverlay,
    showCrewOverlay,
    showFieldObservationsOverlay,
    landingSiteBundle,
    crewPositions,
    fieldObservations,
    sosEvents,
  ]);

  // Camera control handlers (proportional distance-aware zoom + Mars ellipsoid bounds)
  const handleZoom = (factor: number) => {
    const viewer = viewerRef.current;
    const marsEllipsoid = ellipsoidRef.current;
    if (!viewer || !marsEllipsoid) return;
    const carto = marsEllipsoid.cartesianToCartographic(viewer.camera.position);
    if (!carto) return;
    const height = Math.max(5, carto.height);
    if (factor < 1) {
      const step = Math.min(height - 5, Math.max(25, height * (1.0 - factor)));
      if (step > 0) viewer.camera.zoomIn(step);
    } else {
      const step = Math.min(25000000 - height, Math.max(50, height * (factor - 1.0)));
      if (step > 0) viewer.camera.zoomOut(step);
    }
    viewer.scene.requestRender();
  };

  type GlobeCameraPreset = "global" | "regional" | "approach" | "local";
  const handleGlobeCameraPreset = (preset: GlobeCameraPreset) => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    const marsEllipsoid = ellipsoidRef.current;
    if (!viewer || !Cesium || !marsEllipsoid) return;
    const baseLat = selectedDestination?.latitude ?? activeRoute?.vertices[0]?.lat ?? startPoint?.lat ?? -4.749;
    const baseLonRaw = selectedDestination?.normalized_longitude_180 ?? activeRoute?.vertices[0]?.lon_east ?? startPoint?.lon_east ?? 137.397;
    const baseLon = baseLonRaw > 180 ? baseLonRaw - 360 : baseLonRaw;

    if (preset === "global") {
      viewer.camera.flyTo({
        destination: marsEllipsoid.cartographicToCartesian(
          Cesium.Cartographic.fromDegrees(0, 0, GLOBAL_VIEW_CAMERA_HEIGHT_M)
        ),
        orientation: { heading: 0, pitch: -Cesium.Math.PI_OVER_TWO, roll: 0 },
        duration: 0.9,
        complete: () => viewer.scene.requestRender(),
      });
    } else if (preset === "regional") {
      viewer.camera.flyTo({
        destination: marsEllipsoid.cartographicToCartesian(
          Cesium.Cartographic.fromDegrees(baseLon, baseLat, 160000)
        ),
        orientation: { heading: 0, pitch: -Cesium.Math.PI_OVER_TWO, roll: 0 },
        duration: 0.9,
        complete: () => viewer.scene.requestRender(),
      });
    } else if (preset === "approach") {
      viewer.camera.flyTo({
        destination: marsEllipsoid.cartographicToCartesian(
          Cesium.Cartographic.fromDegrees(baseLon, baseLat, 18000)
        ),
        orientation: { heading: 0, pitch: Cesium.Math.toRadians(-55), roll: 0 },
        duration: 0.9,
        complete: () => viewer.scene.requestRender(),
      });
    } else {
      viewer.camera.flyTo({
        destination: marsEllipsoid.cartographicToCartesian(
          Cesium.Cartographic.fromDegrees(baseLon, baseLat, 3500)
        ),
        orientation: { heading: 0, pitch: Cesium.Math.toRadians(-42), roll: 0 },
        duration: 0.9,
        complete: () => viewer.scene.requestRender(),
      });
    }
  };

  const handleResetNorth = () => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    if (!viewer || !Cesium) return;
    viewer.camera.flyTo({
      destination: viewer.camera.positionWC,
      orientation: { heading: 0.0, pitch: viewer.camera.pitch, roll: 0.0 },
      duration: 0.6,
    });
  };

  const handleFocusDestination = () => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    const marsEllipsoid = ellipsoidRef.current;
    if (!viewer || !Cesium || !marsEllipsoid || !selectedDestination) return;
    const currentCartographic = marsEllipsoid.cartesianToCartographic(viewer.camera.position);
    const currentHeight = currentCartographic?.height ?? GLOBAL_VIEW_CAMERA_HEIGHT_M;
    viewer.camera.flyTo({
      destination: marsEllipsoid.cartographicToCartesian(
        Cesium.Cartographic.fromDegrees(selectedDestination.normalized_longitude_180, selectedDestination.latitude, currentHeight)
      ),
      orientation: { heading: 0.0, pitch: -Cesium.Math.PI_OVER_TWO, roll: 0.0 },
      duration: 1.2,
      complete: () => viewer.scene.requestRender(),
    });
  };

  const handleFocusRouteOrRegion = () => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    const marsEllipsoid = ellipsoidRef.current;
    if (!viewer || !Cesium || !marsEllipsoid) return;
    const targetLat = activeRoute?.vertices[0]?.lat ?? startPoint?.lat ?? -4.749;
    const targetLonRaw = activeRoute?.vertices[0]?.lon_east ?? startPoint?.lon_east ?? 137.397;
    const targetLon = targetLonRaw > 180 ? targetLonRaw - 360 : targetLonRaw;
    viewer.camera.flyTo({
      destination: marsEllipsoid.cartographicToCartesian(
        Cesium.Cartographic.fromDegrees(targetLon, targetLat, 8500)
      ),
      orientation: { heading: 0.0, pitch: Cesium.Math.toRadians(-52), roll: 0.0 },
      duration: 1.1,
      complete: () => viewer.scene.requestRender(),
    });
  };

  const handleSwitchMode = (mode: SceneViewMode) => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    if (!viewer || !Cesium) return;
    setViewMode(mode);
    if (mode === "3D") viewer.scene.morphTo3D(0.8);
    else if (mode === "2.5D") viewer.scene.morphToColumbusView(0.8);
    else viewer.scene.morphTo2D(0.8);
    viewer.scene.requestRender();
  };

  return (
    <div className="relative w-full h-full bg-[#06080d] rounded-xl overflow-hidden border border-[#1e2638]">
      <div ref={containerRef} className="w-full h-full" />

      {/* No renderable layers warning */}
      {viewerReady && availableLayers.length === 0 && (
        <div className="absolute inset-0 pointer-events-none flex items-center justify-center p-6 z-10">
          <div className="max-w-md bg-[#0b0d13]/90 border border-amber-500/40 rounded-xl p-5 text-center space-y-2 pointer-events-auto">
            <Layers className="w-7 h-7 text-amber-400 mx-auto" />
            <div className="text-sm font-semibold text-slate-100">
              No Verified Renderable Imagery Layers Active
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              The Mars ellipsoid globe is active (IAU2000:49900), but zero verified map layers have been enabled or processed yet. Verify remote NASA Mars Trek WMTS layers or process a local DEM in the layer drawer or Evidence page.
            </p>
          </div>
        </div>
      )}

      {viewerError && (
        <div className="absolute inset-0 flex items-center justify-center bg-[#0b0d13]/95 p-6 z-20">
          <div className="max-w-md text-center space-y-2 border border-red-500/40 rounded-xl p-5 bg-[#121622]">
            <Globe2 className="w-7 h-7 text-red-400 mx-auto" />
            <div className="text-sm font-bold text-red-300">WebGL Mars Globe Initialization Error</div>
            <p className="text-xs text-slate-400">{viewerError}</p>
          </div>
        </div>
      )}

      {/* Responsive Non-Overlapping Top Controls */}
      <div className="absolute top-2.5 left-2.5 right-2.5 z-10 flex flex-wrap items-start justify-between gap-2 pointer-events-none">
        <div className="flex flex-wrap items-center gap-1.5 pointer-events-auto">
          <div className="flex bg-[#0d111a]/90 backdrop-blur border border-[#1e2638] rounded-lg p-0.5 text-[11px] font-mono">
            {(["3D", "2D", "2.5D"] as SceneViewMode[]).map((m) => (
              <button
                key={m}
                onClick={() => handleSwitchMode(m)}
                className={`px-2.5 py-1 rounded transition-colors ${
                  viewMode === m
                    ? "bg-[#e25b38] text-white font-semibold"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {m}
              </button>
            ))}
          </div>

          <button
            onClick={handleFocusDestination}
            disabled={!selectedDestination}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-[#0d111a]/90 backdrop-blur border border-[#1e2638] text-[11px] font-mono text-cyan-300 hover:bg-[#161c2b] transition-colors disabled:opacity-40"
            title="Center camera on the selected destination"
          >
            <Crosshair className="w-3.5 h-3.5" />
            <span>Focus destination</span>
          </button>

          <button
            onClick={handleFocusRouteOrRegion}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-[#0d111a]/90 backdrop-blur border border-[#1e2638] text-[11px] font-mono text-emerald-300 hover:bg-[#161c2b] transition-colors"
            title="Fly camera obliquely into Gale Crater / Active Route DEM zone"
          >
            <RouteIcon className="w-3.5 h-3.5" />
            <span>{activeRoute ? "Focus Route" : "Focus Gale DEM"}</span>
          </button>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-1.5 pointer-events-auto ml-auto">
          <div className="flex items-center gap-1 bg-[#0d111a]/90 backdrop-blur border border-[#1e2638] rounded-lg p-1">
            <button
              onClick={() => handleZoom(0.6)}
              data-testid="globe-zoom-in"
              className="p-1.5 rounded text-slate-300 hover:bg-[#161c2b]"
              title="Zoom in"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => handleZoom(1.6)}
              data-testid="globe-zoom-out"
              className="p-1.5 rounded text-slate-300 hover:bg-[#161c2b]"
              title="Zoom out"
            >
              <Minus className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleResetNorth}
              className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-mono text-slate-300 hover:bg-[#161c2b]"
              title="Reset camera North-up (Camera heading, distinct from route bearing)"
            >
              <Compass
                className="w-3.5 h-3.5 text-[#e25b38]"
                style={{ transform: `rotate(${-cameraTelemetry.headingDeg}deg)` }}
              />
              <span>CAM {Math.round(cameraTelemetry.headingDeg)}° N</span>
            </button>
            <button
              onClick={() => handleGlobeCameraPreset("global")}
              data-testid="globe-reset"
              className="p-1.5 rounded text-slate-300 hover:bg-[#161c2b]"
              title="Return to global Mars view"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="flex items-center gap-1 bg-[#0d111a]/90 backdrop-blur border border-[#1e2638] rounded-lg p-1 text-[10px] font-mono">
            <button
              onClick={() => handleGlobeCameraPreset("global")}
              className="px-2 py-0.5 rounded text-slate-300 hover:bg-[#161c2b]"
            >
              Global
            </button>
            <button
              onClick={() => handleGlobeCameraPreset("regional")}
              className="px-2 py-0.5 rounded text-slate-300 hover:bg-[#161c2b]"
            >
              Regional
            </button>
            <button
              onClick={() => handleGlobeCameraPreset("approach")}
              className="px-2 py-0.5 rounded text-slate-300 hover:bg-[#161c2b]"
            >
              Approach
            </button>
            <button
              onClick={() => handleGlobeCameraPreset("local")}
              className="px-2 py-0.5 rounded text-cyan-300 hover:bg-[#161c2b]"
            >
              Local DEM
            </button>
          </div>
        </div>
      </div>

      {/* Bottom Scale & Live Cursor Coordinate Bar */}
      <div className="absolute bottom-3 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        <div className="bg-[#0d111a]/90 backdrop-blur border border-[#1e2638] rounded-lg px-3 py-1.5 text-[11px] font-mono text-slate-300 flex items-center gap-3 pointer-events-auto">
          <span>
            {cursorCoords
              ? `CURSOR: ${cursorCoords.lat.toFixed(4)}°, ${cursorCoords.lon.toFixed(4)}° E`
              : "CLICK SURFACE TO INSPECT & SELECT"}
          </span>
          <span className="text-slate-600">|</span>
          <span className="text-slate-400">IAU2000:49900 (Planetocentric)</span>
        </div>

        <div className="bg-[#0d111a]/90 backdrop-blur border border-[#1e2638] rounded-lg px-3 py-1.5 text-[11px] font-mono text-slate-300 flex items-center gap-3 pointer-events-auto">
          <span>ALT: {cameraTelemetry.altitudeKm >= 100 ? `${Math.round(cameraTelemetry.altitudeKm)} km` : `${cameraTelemetry.altitudeKm.toFixed(1)} km`}</span>
          <span className="text-slate-600">|</span>
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-10 h-0.5 bg-cyan-400"></span>
            <span>{cameraTelemetry.scaleLabel}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
