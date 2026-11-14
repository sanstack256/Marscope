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
  coverage_verified?: boolean;
  verification_state: VerificationState;
  footprint_provenance?: string | null;
  crs?: string | null;
  longitude_range?: string | null;
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
  unverified_catalog_candidates?: DatasetCoverageMatch[];
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

export type SpeciesCategory = "element" | "oxide" | "mineral" | "mineral_group";

export type CompositionSearchMode =
  | "auto"
  | "element"
  | "mineral"
  | "element_bearing_mineral";

export interface SpeciesRecord {
  canonical_id: string;
  symbol_or_formula: string;
  canonical_name: string;
  category: SpeciesCategory;
  aliases: string[];
  associated_elements: string[];
  parent_group?: string | null;
  child_species: string[];
  atomic_or_molar_mass?: number | null;
  stoichiometric_element?: string | null;
  stoichiometric_mass_fraction?: number | null;
  supported_instruments: string[];
  notes?: string | null;
}

export interface SpeciesResolutionResult {
  raw_query: string;
  normalized_query: string;
  resolved: boolean;
  ambiguous: boolean;
  species?: SpeciesRecord | null;
  candidates: SpeciesRecord[];
  explanation: string;
}

export interface ValidationStageResult {
  stage_number: number;
  stage_name: string;
  passed: boolean;
  detail: string;
}

export interface CompositionEvidence {
  evidence_id: string;
  source_dataset_id: string;
  product_id: string;
  source_record_ref: string;
  instrument_id: string;
  instrument_name: string;
  mission: string;
  processing_level: string;
  calibration_status: string;
  target_name?: string | null;
  sol?: number | null;
  observation_timestamp_utc?: string | null;
  rmc?: string | null;
  canonical_species_id: string;
  canonical_species_name: string;
  species_category: SpeciesCategory;
  raw_species_name: string;
  evidence_type: string;
  evidence_status: string;
  raw_value?: number | null;
  raw_unit?: string | null;
  normalized_value?: number | null;
  normalized_unit?: string | null;
  normalization_formula?: string | null;
  uncertainty_value?: number | null;
  uncertainty_unit?: string | null;
  uncertainty_type?: string | null;
  detection_limit_value?: number | null;
  detection_limit_unit?: string | null;
  quality_flag?: string | null;
  methodology: string;
  provenance_url?: string | null;
  source_reference: string;
  citation?: string | null;
  location_verified: boolean;
  latitude?: number | null;
  longitude_east?: number | null;
  elevation_m?: number | null;
  crs?: string | null;
  latitude_convention?: string | null;
  longitude_direction?: string | null;
  coordinate_source?: string | null;
  coordinate_provenance?: string | null;
  coordinate_uncertainty_m?: number | null;
  validation_stages: ValidationStageResult[];
  validated_at_utc?: string;
  generation_id?: string | null;
}

export interface RankingDimensions {
  evidence_tier_score: number;
  abundance_component: number;
  quality_component: number;
  corroboration_component: number;
  spatial_proximity_component?: number | null;
  composite_rank_score: number;
  score_formula: string;
  rationale: string;
}

export interface RankedCompositionHit {
  evidence: CompositionEvidence;
  match_type: string;
  match_explanation: string;
  distance_from_astronaut_m?: number | null;
  bearing_deg?: number | null;
  supporting_instruments_nearby: string[];
  nearby_observation_count: number;
  ranking: RankingDimensions;
}

export interface CandidateDiscoveryLocation {
  candidate_id: string;
  cluster_label: string;
  latitude: number;
  longitude_east: number;
  elevation_m?: number | null;
  crs: string;
  coordinate_source: string;
  coordinate_uncertainty_m?: number | null;
  distance_from_astronaut_m?: number | null;
  bearing_deg?: number | null;
  matched_evidence_count: number;
  distinct_instruments: string[];
  best_evidence_type: string;
  best_species_id: string;
  best_normalized_value?: number | null;
  best_normalized_unit?: string | null;
  ranking: RankingDimensions;
  evidence_ids: string[];
  target_names: string[];
  sol_range?: string | null;
}

export interface CompositionIndexStatus {
  index_available: boolean;
  active_generation_id?: string | null;
  built_at_utc?: string | null;
  total_validated_evidence: number;
  located_evidence_count: number;
  unlocated_evidence_count: number;
  rejected_record_count: number;
  species_count: number;
  ingested_products_count: number;
  instruments_indexed: string[];
  checksum_valid: boolean;
  rtree_enabled: boolean;
  crism_status: string;
  sqlite_path?: string | null;
  notes: string[];
}

export interface RejectionRecord {
  rejection_id: string;
  source_dataset_id: string;
  product_id: string;
  source_record_ref: string;
  instrument_id: string;
  raw_species?: string | null;
  rejection_stage: number;
  rejection_code: string;
  reason: string;
  raw_payload: Record<string, unknown>;
  rejected_at_utc: string;
}

export interface CompositionSearchResponse {
  query: string;
  index_available: boolean;
  total_matches: number;
  unlocated_matches_count: number;
  results: Record<string, unknown>[];
  hits: RankedCompositionHit[];
  candidate_locations: CandidateDiscoveryLocation[];
  resolution?: SpeciesResolutionResult | null;
  index_status?: CompositionIndexStatus | null;
  astronaut_position_used?: Record<string, unknown> | null;
  unavailable_reason?: string | null;
  scientific_warnings: string[];
}

export type PlanningMode = "conservative" | "balanced" | "science_priority";

export type TargetProvenanceStatus =
  | "evidence_backed"
  | "manual_unverified_administrative";

export interface ScienceTarget {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  elevation_m?: number | null;
  crs?: string;
  geology_type: string;
  scientific_value: number;
  instrument_source: string;
  provenance_product_id: string;
  target_status?: TargetProvenanceStatus;
  evidence_ids?: string[];
  matched_species?: string | null;
  distance_from_astronaut_m?: number | null;
  explanation?: string | null;
  created_at_utc?: string;
}
