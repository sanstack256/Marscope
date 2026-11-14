"use client";

import { useEffect, useRef, useState } from "react";
import type * as CesiumTypes from "cesium";
import { useLayerStore } from "../stores/useLayerStore";
import { useMissionStore } from "../stores/useMissionStore";
import { Compass, Globe2, Layers, Minus, Plus, RotateCcw, Crosshair } from "lucide-react";

type SceneViewMode = "3D" | "2.5D" | "2D";

interface ManagedImageryLayer {
  cesiumLayer: CesiumTypes.ImageryLayer;
  endpoint: string;
}

export function MarsGlobeViewer() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<CesiumTypes.Viewer | null>(null);
  const cesiumRef = useRef<typeof CesiumTypes | null>(null);
  const ellipsoidRef = useRef<CesiumTypes.Ellipsoid | null>(null);
  const managedLayersRef = useRef<Record<string, ManagedImageryLayer>>({});
  const abortControllerRef = useRef<AbortController | null>(null);

  const [viewerReady, setViewerReady] = useState(false);
  const [viewerError, setViewerError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<SceneViewMode>("3D");
  const [cursorCoords, setCursorCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [cameraTelemetry, setCameraTelemetry] = useState<{
    altitudeKm: number;
    headingDeg: number;
    scaleLabel: string;
  }>({ altitudeKm: 7500, headingDeg: 0, scaleLabel: "~1,000 km" });

  const {
    availableLayers,
    layerStates,
    layerOrder,
    markLayerRendered,
    recordTileError,
    clearTileErrors,
  } = useLayerStore();

  const {
    selectedDestination,
    localizationStatus,
    evaluateDestination,
  } = useMissionStore();

  // Initialize CesiumJS Mars Globe once
  useEffect(() => {
    let destroyed = false;
    let handler: CesiumTypes.ScreenSpaceEventHandler | null = null;
    let removeCameraListener: (() => void) | null = null;

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

        const viewer = new Cesium.Viewer(containerRef.current, {
          globe: new Cesium.Globe(marsEllipsoid),
          baseLayer: false,
          terrainProvider: new Cesium.EllipsoidTerrainProvider({ ellipsoid: marsEllipsoid }),
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
          requestRenderMode: false,
        });

        viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#0b0d13");
        viewer.scene.globe.showGroundAtmosphere = false;
        viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#06080d");
        viewer.scene.sun = new Cesium.Sun();
        viewer.scene.globe.enableLighting = false;

        // Initial camera orientation overlooking Eastern Martian Hemisphere (no fake telemetry)
        viewer.camera.setView({
          destination: marsEllipsoid.cartographicToCartesian(
            Cesium.Cartographic.fromDegrees(137.4, -4.9, 6800000.0)
          ),
          orientation: {
            heading: 0.0,
            pitch: -Cesium.Math.PI_OVER_TWO,
            roll: 0.0,
          },
        });

        // Camera telemetry listener (altitude, compass heading, approximate ground scale)
        const updateTelemetry = () => {
          if (!viewer || viewer.isDestroyed()) return;
          const carto = marsEllipsoid.cartesianToCartographic(viewer.camera.position);
          const altKm = carto ? Math.max(0.05, carto.height / 1000.0) : 0;
          const headingDeg = ((Cesium.Math.toDegrees(viewer.camera.heading) % 360) + 360) % 360;
          // Approximate horizontal ground bar width (~15% viewport at nadir)
          const groundSpanKm = altKm * 0.25;
          const scaleLabel =
            groundSpanKm >= 1.0
              ? `${groundSpanKm >= 100 ? Math.round(groundSpanKm) : groundSpanKm.toFixed(1)} km`
              : `${Math.max(10, Math.round(groundSpanKm * 1000))} m`;
          setCameraTelemetry({ altitudeKm: altKm, headingDeg, scaleLabel });
        };

        viewer.camera.changed.addEventListener(updateTelemetry);
        removeCameraListener = () => viewer.camera.changed.removeEventListener(updateTelemetry);
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

        viewerRef.current = viewer;
        setViewerReady(true);
      } catch (err) {
        setViewerError(err instanceof Error ? err.message : "Failed to initialize Mars 3D WebGL engine.");
      }
    }

    initCesium();

    return () => {
      destroyed = true;
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
          recordTileError(lid, tileErr?.message || "Tile load failed");
        });

        const cesiumLayer = imageryCollection.addImageryProvider(provider);
        managed = { cesiumLayer, endpoint: layer.rendering_endpoint };
        managedLayersRef.current[lid] = managed;
        clearTileErrors(lid);
      }

      managed.cesiumLayer.show = state.visible;
      managed.cesiumLayer.alpha = state.opacity;
      markLayerRendered(lid, state.visible);
    });

    // Apply exact z-index stack order in Cesium ImageryLayerCollection
    orderedIds.forEach((lid) => {
      const managed = managedLayersRef.current[lid];
      if (managed && imageryCollection.contains(managed.cesiumLayer)) {
        imageryCollection.raiseToTop(managed.cesiumLayer);
      }
    });
  }, [viewerReady, availableLayers, layerStates, layerOrder, markLayerRendered, recordTileError, clearTileErrors]);

  // Sync Destination & Manual Localization Markers on Globe
  useEffect(() => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    const marsEllipsoid = ellipsoidRef.current;
    if (!viewerReady || !viewer || viewer.isDestroyed() || !Cesium || !marsEllipsoid) return;

    viewer.entities.removeAll();

    if (selectedDestination) {
      const pos = marsEllipsoid.cartographicToCartesian(
        Cesium.Cartographic.fromDegrees(selectedDestination.normalized_longitude_180, selectedDestination.latitude, 500)
      );
      viewer.entities.add({
        id: "selected-destination",
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
        Cesium.Cartographic.fromDegrees(activePos.longitude, activePos.latitude, 500)
      );
      viewer.entities.add({
        id: "explorer-position",
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
  }, [viewerReady, selectedDestination, localizationStatus]);

  // Camera control handlers
  const handleZoom = (factor: number) => {
    const viewer = viewerRef.current;
    const marsEllipsoid = ellipsoidRef.current;
    if (!viewer || !marsEllipsoid) return;
    const carto = marsEllipsoid.cartesianToCartographic(viewer.camera.position);
    if (!carto) return;
    const dist = Math.max(2000, carto.height * factor);
    if (factor < 1) viewer.camera.zoomIn(dist);
    else viewer.camera.zoomOut(dist);
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

  const handleFocusStudyCandidate = () => {
    const viewer = viewerRef.current;
    const Cesium = cesiumRef.current;
    const marsEllipsoid = ellipsoidRef.current;
    if (!viewer || !Cesium || !marsEllipsoid) return;
    viewer.camera.flyTo({
      destination: marsEllipsoid.cartographicToCartesian(
        Cesium.Cartographic.fromDegrees(137.45, -4.9, 120000.0)
      ),
      orientation: { heading: 0.0, pitch: -Cesium.Math.PI_OVER_TWO, roll: 0.0 },
      duration: 1.2,
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

      {/* Top-Left View & Perspective Controls */}
      <div className="absolute top-3 left-3 z-10 flex flex-wrap items-center gap-1.5">
        <div className="flex bg-[#0d111a]/90 backdrop-blur border border-[#1e2638] rounded-lg p-0.5 text-[11px] font-mono">
          {(["3D", "2.5D", "2D"] as SceneViewMode[]).map((m) => (
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
          onClick={handleFocusStudyCandidate}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-[#0d111a]/90 backdrop-blur border border-[#1e2638] text-[11px] font-mono text-cyan-300 hover:bg-[#161c2b] transition-colors"
          title="Center camera over Gale Crater candidate region without changing selected destination"
        >
          <Crosshair className="w-3.5 h-3.5" />
          <span>Gale View</span>
        </button>
      </div>

      {/* Top-Right Compass & Zoom Controls */}
      <div className="absolute top-3 right-3 z-10 flex flex-col items-end gap-2">
        <div className="flex items-center gap-1 bg-[#0d111a]/90 backdrop-blur border border-[#1e2638] rounded-lg p-1">
          <button
            onClick={() => handleZoom(0.4)}
            className="p-1.5 rounded text-slate-300 hover:bg-[#161c2b]"
            title="Zoom in"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => handleZoom(0.65)}
            className="p-1.5 rounded text-slate-300 hover:bg-[#161c2b]"
            title="Zoom out"
          >
            <Minus className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleResetNorth}
            className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-mono text-slate-300 hover:bg-[#161c2b]"
            title="Reset camera North-up"
          >
            <Compass
              className="w-3.5 h-3.5 text-[#e25b38]"
              style={{ transform: `rotate(${-cameraTelemetry.headingDeg}deg)` }}
            />
            <span>{Math.round(cameraTelemetry.headingDeg)}° N</span>
          </button>
          <button
            onClick={() => {
              if (!viewerRef.current || !cesiumRef.current || !ellipsoidRef.current) return;
              viewerRef.current.camera.flyTo({
                destination: ellipsoidRef.current.cartographicToCartesian(
                  cesiumRef.current.Cartographic.fromDegrees(137.4, -4.9, 6800000.0)
                ),
                duration: 0.9,
              });
            }}
            className="p-1.5 rounded text-slate-300 hover:bg-[#161c2b]"
            title="Reset planetary orbital view"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
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
            <span>~{cameraTelemetry.scaleLabel}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
