/**
 * MARSCOPE Domain Type Definitions (Matching Backend Pydantic Schemas)
 */

export type VerificationState =
  | "verified"
  | "unverified"
  | "pending"
  | "unknown"
  | "failed"
  | "not_applicable";

export interface SystemHealth {
  status: string;
  system: string;
  version: string;
  environment: string;
  timestamp_utc: string;
  engines: {
    physics: string;
    geospatial: string;
    terrain: string;
    routing: string;
  };
}

export interface MetadataVerification {
  archive_availability: VerificationState;
  product_discovery: VerificationState;
  metadata_verification: VerificationState;
  license_verification: VerificationState;
  coverage_verification: VerificationState;
  download_verification: VerificationState;
  processing_verification: VerificationState;
  field_verification: Record<string, VerificationState>;
  evidence_notes: string[];
  last_checked_utc?: string | null;
}

export interface GeographicCoverage {
  min_latitude: number;
  max_latitude: number;
  min_longitude: number;
  max_longitude: number;
  center_latitude?: number | null;
  center_longitude?: number | null;
  longitude_range: string;
}

export interface Dataset {
  id: string;
  product_id: string;
  product_title: string;
  product_type: string;
  mission: string;
  instrument: string;
  source_archive: string;
  original_product_url: string;
  original_label_url?: string | null;
  doi_or_pds_id?: string | null;
  license: string;
  attribution: string;
  acquisition_timestamp?: string | null;
  observation_sol?: number | null;
  processing_level: string;
  calibration_status: string;
  coverage: GeographicCoverage;
  coordinate_reference_system?: string | null;
  latitude_convention: string;
  longitude_direction: string;
  map_projection: string;
  horizontal_resolution_meters?: number | null;
  vertical_resolution_meters?: number | null;
  units: string;
  nodata_value?: number | null;
  data_format: string;
  file_size_bytes?: number | null;
  sha256_checksum?: string | null;
  status: string;
  verification: MetadataVerification;
  failure_reason?: string | null;
  quality_flags: string[];
  known_limitations: string[];
  processing_history: string[];
  local_file_path?: string | null;
  processed_file_path?: string | null;
}

export interface LayerLegendStop {
  value: string;
  color: string;
  label: string;
}

export interface LayerLegend {
  title: string;
  units: string;
  min_value?: number | null;
  max_value?: number | null;
  stops: LayerLegendStop[];
}

export interface MapLayer {
  layer_id: string;
  display_name: string;
  layer_type: string;
  category: string;
  source_dataset_id: string;
  source_product_id: string;
  data_type: string;
  units: string;
  crs: string;
  spatial_bounds: number[];
  spatial_resolution_m?: number | null;
  acquisition_date?: string | null;
  processing_level: string;
  processing_version: string;
  valid_data_coverage_pct?: number | null;
  nodata_coverage_pct?: number | null;
  attribution: string;
  license: string;
  verification_state: VerificationState;
  renderable: boolean;
  rendering_endpoint?: string | null;
  tile_scheme?: string | null;
  maximum_zoom?: number | null;
  default_visible: boolean;
  default_opacity: number;
  known_limitations: string[];
  unavailable_reason?: string | null;
  legend?: LayerLegend | null;
}

export interface LayerCatalogResponse {
  available_layers: MapLayer[];
  unavailable_layers: MapLayer[];
  total_available: number;
  total_unavailable: number;
}

export interface RasterBandStats {
  available: boolean;
  min_value?: number | null;
  max_value?: number | null;
  mean_value?: number | null;
  std_dev?: number | null;
  valid_pixel_count: number;
  nodata_pixel_count: number;
  valid_data_percentage: number;
  units: string;
}

export interface TerrainSummary {
  source_dem_id: string;
  source_product_id?: string | null;
  processing_version: string;
  study_area_name: string;
  resolution_meters_per_pixel: number;
  roughness_window_radius_meters?: number | null;
  crs: string;
  elevation_stats: RasterBandStats;
  slope_stats: RasterBandStats;
  aspect_stats?: RasterBandStats | null;
  roughness_stats?: RasterBandStats | null;
  critical_slope_threshold_deg: number;
  critical_slope_coverage_pct?: number | null;
  quality_warnings: string[];
}

export interface TerrainSummaryResponse {
  available: boolean;
  unavailable_reason?: string | null;
  summary?: TerrainSummary | null;
}

export interface TerrainPointResponse {
  available: boolean;
  latitude: number;
  longitude: number;
  crs: string;
  latitude_convention: string;
  longitude_direction: string;
  elevation_m?: number | null;
  slope_deg?: number | null;
  aspect_deg?: number | null;
  roughness_tri_m?: number | null;
  source_dataset_id?: string | null;
  source_product_id?: string | null;
  resolution_m?: number | null;
  units?: string | null;
  unavailable_reason?: string | null;
  warnings: string[];
}

export interface Observation {
  observation_id: string;
  dataset_id: string;
  mission: string;
  instrument: string;
  observation_timestamp?: string | null;
  sol?: number | null;
  location?: {
    latitude: number;
    longitude: number;
    elevation_m?: number | null;
  } | null;
  crs?: string | null;
  measurement_type: string;
  measurement_value: Record<string, unknown>;
  units: string;
  processing_level: string;
  calibration_status: string;
  quality_flags: string[];
  original_source_reference: string;
  known_limitations: string[];
}

export interface PhysicsParameter {
  id: string;
  name: string;
  value: number;
  units: string;
  source: string;
  source_url: string;
  validity_range?: number[] | null;
  applicable_conditions: string;
  uncertainty?: number | null;
  version: string;
  verification_status: string;
}

export interface PhysicsModelDescriptor {
  model_name: string;
  equation: string;
  required_inputs: string[];
  output_units: string;
  description: string;
}

export interface PhysicsCalculationResult {
  model_name: string;
  model_version: string;
  calculated_value: number;
  units: string;
  inputs: Record<string, unknown>;
  scientific_references: string[];
  engineering_assumptions: string[];
  uncertainty?: number | null;
  validity_warnings: string[];
}

export interface SourceRegistryEntry {
  source_name: string;
  base_url: string;
  product_count: number;
  product_ids: string[];
  verification_breakdown: {
    archive_availability: string;
    product_discovery: string;
    metadata_verification: string;
    license_verification: string;
    coverage_verification: string;
    download_verification: string;
    processing_verification: string;
  };
  licenses: string[];
  evidence_notes: string[];
}

export interface PositionRecord {
  position_source: "mission_live_feed" | "suit_rover_telemetry" | "manual_selection" | "test_fixture" | "unavailable";
  latitude?: number | null;
  longitude?: number | null;
  elevation_m?: number | null;
  crs: string;
  latitude_convention: string;
  longitude_direction: string;
  timestamp_utc?: string | null;
  accuracy_meters?: number | null;
  validity_state: "valid" | "unverified" | "stale" | "unavailable";
  provenance: string;
  notes: string[];
}

export interface LocalizationStatusResponse {
  live_localization_available: boolean;
  active_provider: string;
  unavailable_reason?: string | null;
  current_position?: PositionRecord | null;
  supported_providers: {
    provider_id: string;
    provider_type: string;
    name: string;
    connected: boolean;
    status_detail: string;
  }[];
}

export interface DatasetCoverageMatch {
  dataset_id: string;
  product_id: string;
  product_title: string;
  product_type: string;
  horizontal_resolution_meters?: number | null;
  available_for_evaluation: boolean;
  verification_state: VerificationState;
  notes?: string | null;
}

export interface DestinationEvaluationResponse {
  valid: boolean;
  latitude: number;
  longitude: number;
  normalized_longitude_180: number;
  normalized_longitude_360: number;
  crs: string;
  latitude_convention: string;
  longitude_direction: string;
  label?: string | null;
  can_evaluate: boolean;
  evaluation_status: string;
  covering_datasets: DatasetCoverageMatch[];
  terrain: {
    available: boolean;
    elevation_m?: number | null;
    slope_deg?: number | null;
    aspect_deg?: number | null;
    roughness_tri_m?: number | null;
    source_dataset_id?: string | null;
    source_product_id?: string | null;
    resolution_m?: number | null;
    units?: string | null;
    crs?: string | null;
    unavailable_reason?: string | null;
    warnings: string[];
  };
  warnings: string[];
  selected_at_utc: string;
}

export interface CompositionSearchResponse {
  query: string;
  index_available: boolean;
  total_matches: number;
  results: unknown[];
  unavailable_reason?: string | null;
}

export type PlanningMode = "conservative" | "balanced" | "science_priority";

export interface ScienceTarget {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  elevation_m?: number | null;
  geology_type: string;
  scientific_value: number;
  instrument_source: string;
  provenance_product_id: string;
}
