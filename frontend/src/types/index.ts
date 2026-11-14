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

export interface PlanningSlopeThreshold {
  threshold_deg: number;
  parameter_class: string;
  label: string;
  provenance: string;
  version: string;
  is_validated_safety_limit: boolean;
}

export interface InsufficientCoverageReport {
  status?: string;
  requested_bounds: Record<string, number>;
  requested_bounds_modified: boolean;
  source_coverage_bounds?: Record<string, number> | null;
  intersecting_bounds?: Record<string, number> | null;
  requested_pixel_dimensions?: Record<string, number | null> | null;
  available_pixel_dimensions?: Record<string, number> | null;
  source_resolution?: Record<string, unknown> | null;
  minimum_resolution_requirement: Record<string, unknown>;
  insufficient_coverage_reason: string;
  supported_products: string[];
  unsupported_derivative_products: string[];
  next_action: string;
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
  planning_threshold?: PlanningSlopeThreshold | null;
  planning_threshold_coverage_pct?: number | null;
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

export type LocationSemanticType =
  | "instrument_target_location"
  | "rover_station_location"
  | "product_footprint"
  | "observation_region"
  | "unlocated";

export type IntegrityStatus =
  | "verified"
  | "source_files_missing"
  | "checksum_mismatch"
  | "manifest_invalid"
  | "stale"
  | "incomplete"
  | "unavailable";

export type RightsStatus =
  | "verified"
  | "not_verified"
  | "not_found"
  | "restricted_conditions_apply";

export type GenerationBuildStatus =
  | "complete"
  | "complete_with_declared_unavailable_sources"
  | "partial"
  | "failed";

export type MeasurementCategory =
  | "direct_elemental_concentration"
  | "oxide_derived_elemental_concentration"
  | "direct_oxide_concentration"
  | "mineral_weight_percent"
  | "mineral_group_membership_evidence";

export interface UncertaintyMetadata {
  reported_value?: number | null;
  reported_unit?: string | null;
  normalized_value?: number | null;
  normalized_unit?: string | null;
  is_physical_unit?: boolean;
  source_field_name?: string | null;
  source_data_type?: string | null;
  schema_identity?: string | null;
  uncertainty_type: string;
  statistical_interpretation: string;
  coverage_confidence_level: string;
  source_definition: string;
  source_product: string;
  conversion_history?: string[];
  limitations?: string[];
}

export interface RelativeUncertaintySummary {
  available: boolean;
  value?: number | null;
  percent?: number | null;
  numerator_uncertainty?: number | null;
  numerator_unit?: string | null;
  denominator_measurement?: number | null;
  denominator_unit?: string | null;
  uncertainty_type?: string | null;
  statistical_interpretation?: string | null;
  conversion_history?: string[];
  calculation_formula: string;
  calculation_version: string;
  unavailable_reason?: string | null;
}

export interface SourceArtifactRecord {
  artifact_id: string;
  artifact_role: string;
  dataset_id: string;
  product_id: string;
  file_path: string;
  required: boolean;
  present: boolean;
  verified: boolean;
  sha256_checksum?: string | null;
  byte_size?: number | null;
  retrieval_timestamp_utc: string;
  source_mtime_utc?: string | null;
  source_url?: string | null;
  license_status: RightsStatus;
  rights_statement?: string | null;
  failure_reason?: string | null;
}

export interface ProductAuditEntry {
  dataset_id: string;
  product_id: string;
  expected_artifact_name: string;
  discovery_scope: string;
  present_locally: boolean;
  build_status: string;
  accepted_record_count: number;
  rejected_record_count: number;
  companion_dependencies: string[];
  failure_reason?: string | null;
}

export interface CompositionEvidence {
  evidence_id: string;
  determinism_version?: string;
  source_dataset_id: string;
  product_id: string;
  source_record_ref: string;
  source_file_checksum?: string | null;
  source_artifact_dependency_digest?: string | null;
  companion_schema_checksums?: Record<string, string>;
  schema_version?: string | null;
  parser_id?: string | null;
  parser_version?: string | null;
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
  value_semantics?: string;
  source_raw_token?: string | null;
  source_interpretation_note?: string | null;
  source_special_constants?: Record<string, string> | null;
  raw_value?: number | null;
  raw_unit?: string | null;
  normalized_value?: number | null;
  normalized_unit?: string | null;
  normalization_formula?: string | null;
  is_stoichiometric_conversion?: boolean;
  source_oxide_species?: string | null;
  stoichiometric_factor?: number | null;
  stoichiometric_weights_version?: string | null;
  uncertainty_value?: number | null;
  uncertainty_unit?: string | null;
  uncertainty_type?: string | null;
  uncertainty_semantics?: string | null;
  uncertainty_metadata?: UncertaintyMetadata | null;
  secondary_uncertainty_value?: number | null;
  secondary_uncertainty_unit?: string | null;
  secondary_uncertainty_type?: string | null;
  secondary_uncertainty_metadata?: UncertaintyMetadata | null;
  instrument_standoff_m?: number | null;
  detection_limit_value?: number | null;
  detection_limit_unit?: string | null;
  detection_limit_status?: string | null;
  quality_flag?: string | null;
  methodology: string;
  provenance_url?: string | null;
  source_reference: string;
  citation?: string | null;
  location_verified: boolean;
  location_semantic_type?: LocationSemanticType;
  latitude?: number | null;
  longitude_east?: number | null;
  elevation_m?: number | null;
  crs?: string | null;
  latitude_convention?: string | null;
  longitude_direction?: string | null;
  coordinate_source?: string | null;
  coordinate_provenance?: string | null;
  coordinate_uncertainty_m?: number | null;
  original_coordinate_values?: Record<string, unknown> | null;
  original_coordinate_crs?: string | null;
  coordinate_transform?: string | null;
  coordinate_transform_params?: Record<string, unknown> | null;
  waypoint_id?: string | null;
  association_rule_version?: string | null;
  coordinate_limitations?: string[];
  validation_stages: ValidationStageResult[];
  validated_at_utc?: string;
  generation_id?: string | null;
}

export interface RankingDimensions {
  ranking_config_id?: string;
  ranking_config_version?: string;
  is_heuristic_only?: boolean;
  ranking_methodology_label?: string;
  evidence_tier_score: number;
  abundance_component?: number | null;
  quality_component?: number | null;
  corroboration_component?: number | null;
  spatial_proximity_component?: number | null;
  composite_rank_score?: number | null;
  unavailable_dimensions?: string[];
  uncertainty_compatibility_status?: string;
  quality_exclusion_reason?: string | null;
  relative_uncertainty?: RelativeUncertaintySummary | null;
  score_formula: string;
  rationale: string;
}

export interface RankedCompositionHit {
  evidence: CompositionEvidence;
  match_type: string;
  measurement_category?: MeasurementCategory | null;
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
  location_semantic_type?: LocationSemanticType;
  coordinate_uncertainty_m?: number | null;
  coordinate_limitations?: string[];
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

export interface ProductManifestEntry {
  dataset_id: string;
  product_id: string;
  file_path: string;
  sha256_checksum: string;
  byte_size?: number;
  retrieval_timestamp_utc?: string;
  source_mtime_utc?: string | null;
  source_url?: string | null;
  license?: string | null;
  license_status?: RightsStatus;
  rights_statement?: string | null;
  label_path?: string | null;
  dependency_digest?: string | null;
  companion_files?: Record<string, string>;
  schema_version?: string | null;
  parser_id?: string | null;
  parser_version?: string | null;
  validation_pipeline_version?: string | null;
  determinism_version?: string | null;
  coordinate_association_method?: string | null;
  record_count?: number;
  rejected_count?: number;
}

export interface CompositionIndexStatus {
  index_available: boolean;
  integrity_status?: IntegrityStatus;
  generation_build_status?: GenerationBuildStatus;
  source_integrity_status?: IntegrityStatus;
  manifest_integrity_status?: IntegrityStatus;
  pointer_integrity_status?: IntegrityStatus;
  database_integrity_status?: IntegrityStatus;
  active_generation_id?: string | null;
  previous_successful_generation_id?: string | null;
  incomplete_staging_generations?: string[];
  source_artifact_digest?: string | null;
  complete_manifest_digest?: string | null;
  built_at_utc?: string | null;
  publication_timestamp_utc?: string | null;
  pointer_path?: string | null;
  total_validated_evidence: number;
  located_evidence_count: number;
  unlocated_evidence_count: number;
  rejected_record_count: number;
  species_count: number;
  ingested_products_count: number;
  expected_products_count?: number;
  discovery_scope?: string;
  instruments_indexed: string[];
  checksum_valid: boolean;
  source_dependencies_valid?: boolean;
  manifest_valid?: boolean;
  missing_source_files?: string[];
  checksum_mismatches?: string[];
  missing_dependency_files?: string[];
  dependency_checksum_mismatches?: string[];
  missing_expected_products?: string[];
  manifest_validation_errors?: string[];
  reproducibility_manifest_path?: string | null;
  product_manifests?: ProductManifestEntry[];
  dependency_artifacts?: SourceArtifactRecord[];
  product_audit?: ProductAuditEntry[];
  rights_summary?: {
    counts?: Record<string, number>;
    note?: string;
  };
  retrieval_metadata?: {
    total_tracked_artifacts?: number;
    verified_retrieval_timestamps?: number;
    unknown_retrieval_timestamps?: number;
    discovery_scope?: string;
    note?: string;
  };
  rtree_enabled: boolean;
  crism_status: string;
  sqlite_path?: string | null;
  notes: string[];
}

export interface ReproducibilityManifest {
  manifest_format_version: string;
  generation_id: string;
  generation_build_status?: GenerationBuildStatus;
  discovery_scope?: string;
  built_at_utc?: string;
  publication_timestamp_utc?: string;
  publication_nonce?: string;
  previous_successful_generation_id?: string | null;
  source_artifact_digest?: string;
  complete_manifest_digest?: string;
  source_manifest_checksum?: string;
  determinism_version: string;
  validation_pipeline_version?: string;
  ranking_config_id?: string;
  ranking_config_version?: string;
  total_validated_evidence?: number;
  located_evidence_count?: number;
  unlocated_evidence_count?: number;
  rejected_record_count?: number;
  crism_status?: string;
  rights_summary?: {
    counts?: Record<string, number>;
    note?: string;
  };
  retrieval_metadata?: {
    total_tracked_artifacts?: number;
    verified_retrieval_timestamps?: number;
    unknown_retrieval_timestamps?: number;
    discovery_scope?: string;
    note?: string;
  };
  products: ProductManifestEntry[];
  dependency_artifacts?: SourceArtifactRecord[];
  product_audit?: ProductAuditEntry[];
  missing_expected_products?: string[];
  notes?: string[];
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
  measurement_categories_present?: MeasurementCategory[];
  grouped_counts_by_measurement_category?: Record<string, number>;
  applied_filter_scope_note?: string | null;
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

export interface ScaleSuitabilityRecord {
  analysis_type: string;
  suitability: string;
  native_resolution_m?: number | null;
  effective_resolution_m?: number | null;
  minimum_recommended_resolution_m: number;
  policy_id?: string | null;
  policy_version?: string | null;
  threshold_classification?: string | null;
  threshold_rationale?: string | null;
  supported: boolean;
  explanation: string;
  scientific_limitation: string;
}

export interface TerrainDatasetInventoryEntry {
  dataset_id: string;
  product_id: string;
  product_title: string;
  mission: string;
  instrument: string;
  source_archive: string;
  source_url: string;
  status: string;
  locally_downloaded: boolean;
  locally_processed: boolean;
  crs: string;
  vertical_units: string;
  native_horizontal_resolution_m?: number | null;
  effective_equatorial_pixel_m?: number | null;
  coverage_bounds: Record<string, number>;
  sha256_checksum?: string | null;
  resolution_suitability: Record<string, ScaleSuitabilityRecord>;
  limitations: string[];
}

export interface MobilityStatusResponse {
  engine_name: string;
  engine_version: string;
  route_optimization_enabled: boolean;
  safety_certification_enabled: boolean;
  active_dem_dataset_id?: string | null;
  total_catalog_dem_count: number;
  locally_downloaded_dem_count: number;
  locally_processed_dem_count: number;
  scenario_count: number;
  terrain_inventory: TerrainDatasetInventoryEntry[];
  capabilities: string[];
  scientific_limitations: string[];
}

export interface CoverageIntelligenceResponse {
  dataset_id: string;
  source_product_id: string;
  crs: string;
  requested_bounds: Record<string, number>;
  requested_bounds_modified: boolean;
  source_footprint_bounds: Record<string, number>;
  overlap_bounds?: Record<string, number> | null;
  has_spatial_overlap: boolean;
  sufficient_for_3x3_derivatives: boolean;
  requested_area_km2: number;
  covered_area_km2: number;
  uncovered_area_km2: number;
  valid_elevation_area_km2: number;
  nodata_elevation_area_km2: number;
  valid_derivative_area_km2: number;
  valid_elevation_percentage_of_requested: number;
  valid_derivative_percentage_of_requested: number;
  pixel_counts: Record<string, number>;
  coverage_state_counts: Record<string, number>;
  derivative_availability: Record<string, boolean>;
  resolution_suitability: Record<string, ScaleSuitabilityRecord>;
  insufficient_coverage_report?: InsufficientCoverageReport | null;
  notes: string[];
}

export interface ElevationProfileSample {
  sample_index: number;
  lat: number;
  lon_east: number;
  cumulative_distance_meters: number;
  segment_distance_meters: number;
  coverage_state: string;
  elevation_meters?: number | null;
  segment_elevation_delta_meters?: number | null;
  slope_deg?: number | null;
  segment_slope_deg?: number | null;
  aspect_deg?: number | null;
  roughness_tri_meters?: number | null;
  source_pixel_row?: number | null;
  source_pixel_col?: number | null;
}

export interface ElevationProfileGapSegment {
  start_sample_index: number;
  end_sample_index: number;
  start_distance_meters: number;
  end_distance_meters: number;
  gap_length_meters: number;
  reason: string;
}

export interface ElevationProfileResponse {
  dataset_id: string;
  source_product_id: string;
  crs: string;
  sampling_method: string;
  geometry_type: string;
  waypoint_count: number;
  sample_count: number;
  valid_sample_count: number;
  nodata_sample_count: number;
  complete_coverage: boolean;
  sample_spacing_meters: number;
  total_horizontal_distance_meters: number;
  evaluated_horizontal_distance_meters: number;
  total_positive_elevation_gain_meters?: number | null;
  total_negative_elevation_change_meters?: number | null;
  net_elevation_change_meters?: number | null;
  min_elevation_meters?: number | null;
  max_elevation_meters?: number | null;
  mean_slope_along_profile_deg?: number | null;
  max_slope_along_profile_deg?: number | null;
  nodata_gap_segments: ElevationProfileGapSegment[];
  samples: ElevationProfileSample[];
  resolution_suitability: Record<string, ScaleSuitabilityRecord>;
  limitations: string[];
}

export interface MobilityScenario {
  scenario_id: string;
  name: string;
  version: string;
  description?: string | null;
  created_at_utc: string;
  is_safety_certification: boolean;
  mars_surface_gravity_m_s2: number;
  reference_walking_speed_m_per_s?: number | null;
  planning_max_slope_deg?: number | null;
  planning_max_roughness_m?: number | null;
  roughness_window_radius_m?: number | null;
  astronaut_body_mass_kg?: number | null;
  suit_mass_kg?: number | null;
  carried_load_mass_kg?: number | null;
  total_mass_kg?: number | null;
  mars_surface_weight_n?: number | null;
  traversal_time_estimation_ready: boolean;
  notes: string[];
}

export interface MobilityEvaluationResponse {
  evaluation_id: string;
  evaluation_mode: string;
  dataset_id: string;
  source_product_id: string;
  processing_version: string;
  traversal_model_id: string;
  traversal_model_version: string;
  scenario: MobilityScenario;
  physical_measurements: Record<string, unknown>;
  scenario_traversal_estimates: Record<string, unknown>;
  coverage_intelligence?: CoverageIntelligenceResponse | null;
  elevation_profile?: ElevationProfileResponse | null;
  cost_surface?: Record<string, unknown> | null;
  resolution_suitability: Record<string, ScaleSuitabilityRecord>;
  scientific_limitations: string[];
}

// ============================================================
// Prompt 11: Real 3D Terrain Mesh & Science-Aware Routing
// ============================================================

export type TextureOverlayMode = "ortho" | "elevation" | "slope" | "roughness";
export type SurfacePickMode = "inspect" | "set_start" | "add_waypoint" | "set_destination";
export type PathAlgorithm = "astar" | "dijkstra";

export interface MeshDemSummary {
  dataset_id: string;
  product_id: string;
  product_title: string;
  native_resolution_m?: number | null;
  ortho_dataset_id?: string | null;
  bounds: Record<string, number>;
  recommended_focus_bounds: Record<string, number>;
  local_slope_suitable: boolean;
}

export interface MeshLodLevel {
  lod: number;
  tiles_x: number;
  tiles_y: number;
  tile_grid_cols: number;
  tile_grid_rows: number;
  approx_vertex_spacing_m: number;
}

export interface MeshTileDescriptor {
  tile_id: string;
  lod: number;
  row: number;
  col: number;
  bounds: Record<string, number>;
  grid_rows: number;
  grid_cols: number;
  approx_vertex_spacing_m: number;
}

export interface TerrainMeshManifest {
  dataset_id: string;
  product_id: string;
  product_title: string;
  crs: string;
  vertical_units: string;
  vertical_datum: string;
  native_resolution_m?: number | null;
  ortho_dataset_id?: string | null;
  requested_bounds: Record<string, number>;
  requested_bounds_modified: boolean;
  dataset_bounds: Record<string, number>;
  origin: { lat: number; lon_east: number };
  physical_extent_m: { width_m: number; height_m: number };
  lod_levels: MeshLodLevel[];
  tiles: MeshTileDescriptor[];
  available_dems: MeshDemSummary[];
  resolution_suitability: Record<string, ScaleSuitabilityRecord>;
  elevation_range_m?: { min_m: number; max_m: number } | null;
  roughness_range_m?: { min_m: number; max_m: number } | null;
}

export interface TerrainMeshTile {
  tile_id: string;
  dataset_id: string;
  product_id: string;
  crs: string;
  vertical_units: string;
  bounds: Record<string, number>;
  origin: { lat: number; lon_east: number };
  local_bounds_m: {
    min_east_m: number;
    max_east_m: number;
    min_north_m: number;
    max_north_m: number;
  };
  grid_rows: number;
  grid_cols: number;
  sample_spacing_m: { dx_m: number; dy_m: number };
  native_resolution_m?: number | null;
  elevations_m: (number | null)[];
  valid_mask: number[];
  normals?: number[] | null;
  slope_deg?: (number | null)[] | null;
  roughness_tri_m?: (number | null)[] | null;
  valid_vertex_count: number;
  nodata_vertex_count: number;
  elevation_min_m?: number | null;
  elevation_max_m?: number | null;
  slope_max_deg?: number | null;
  generation_ms: number;
}

export interface RouteCoordinateInput {
  lat: number;
  lon_east: number;
  label?: string | null;
  target_id?: string | null;
}

export interface RoutePlanningConstraints {
  max_slope_deg: number;
  max_roughness_tri_m?: number | null;
  snap_radius_m: number;
  walking_speed_m_per_s?: number | null;
  walking_speed_provenance?: string | null;
  astronaut_total_mass_kg?: number | null;
  max_eva_duration_hours?: number | null;
  safety_reserve_fraction: number;
  enforce_budget: boolean;
  return_to_start: boolean;
  optimize_target_order: boolean;
  simplification_epsilon_m: number;
  max_grid_dim: number;
}

export interface SnapDiagnostic {
  point_role: string;
  requested_lat: number;
  requested_lon_east: number;
  snapped: boolean;
  snapped_lat: number;
  snapped_lon_east: number;
  snap_distance_m: number;
  source_cell_state: string;
  elevation_m?: number | null;
}

export interface SimplificationDiagnostic {
  raw_grid_nodes: number;
  simplified_vertices: number;
  segments_checked: number;
  shortcuts_accepted: number;
  shortcuts_rejected_obstacle_or_nodata: number;
  all_simplified_segments_verified_valid: boolean;
}

export interface BudgetDiagnostic {
  evaluated: boolean;
  return_to_start_included: boolean;
  max_eva_duration_seconds?: number | null;
  safety_reserve_fraction: number;
  usable_budget_seconds?: number | null;
  estimated_total_duration_seconds?: number | null;
  margin_seconds?: number | null;
  within_budget?: boolean | null;
  reason?: string | null;
}

export interface RouteVertex {
  seq: number;
  lat: number;
  lon_east: number;
  elevation_m: number;
  slope_deg?: number | null;
  roughness_tri_m?: number | null;
  cumulative_distance_m: number;
  segment_distance_m: number;
  is_stop: boolean;
  stop_role?: string | null;
  stop_label?: string | null;
  target_id?: string | null;
  science_corridor_score: number;
}

export interface RouteLegSummary {
  leg_index: number;
  from_label: string;
  to_label: string;
  is_return_leg: boolean;
  horizontal_distance_m: number;
  surface_distance_m: number;
  elevation_gain_m: number;
  elevation_loss_m: number;
  mean_slope_deg: number;
  max_slope_deg: number;
  mean_roughness_tri_m?: number | null;
  estimated_duration_seconds?: number | null;
  total_cost: number;
  vertex_start_seq: number;
  vertex_end_seq: number;
}

export interface NavigationInstruction {
  step_index: number;
  action: string;
  bearing_true_north_deg?: number | null;
  bearing_grid_north_deg?: number | null;
  cardinal_direction?: string | null;
  turn_angle_deg?: number | null;
  from_lat: number;
  from_lon_east: number;
  to_lat: number;
  to_lon_east: number;
  segment_distance_m: number;
  cumulative_distance_m: number;
  elevation_start_m: number;
  elevation_end_m: number;
  elevation_delta_m: number;
  grade_percent: number;
  segment_slope_deg: number;
  local_roughness_tri_m?: number | null;
  terrain_context: string;
  nearby_science_targets: string[];
  caution_notes: string[];
  instruction_text: string;
}

export interface ScienceStopSummary {
  target_id?: string | null;
  name: string;
  lat: number;
  lon_east: number;
  geology_type?: string | null;
  scientific_value?: number | null;
  matched_species?: string | null;
  instrument_source?: string | null;
  visit_order_index: number;
  distance_from_route_m: number;
}

export interface RouteComputeResponse {
  route_id: string;
  route_signature: string;
  created_at_utc: string;
  dataset_id: string;
  source_product_id: string;
  crs: string;
  bearing_convention: string;
  mode: PlanningMode;
  mode_label: string;
  algorithm: PathAlgorithm;
  effective_slope_limit_deg: number;
  native_dem_resolution_m: number;
  solver_grid_spacing_m: number;
  solver_grid_shape: { rows: number; cols: number };
  assumption_classification: string;
  return_to_start: boolean;
  within_budget?: boolean | null;
  budget_diagnostic: BudgetDiagnostic;
  total_horizontal_distance_m: number;
  total_surface_distance_m: number;
  total_elevation_gain_m: number;
  total_elevation_loss_m: number;
  net_elevation_change_m: number;
  min_elevation_m: number;
  max_elevation_m: number;
  mean_slope_deg: number;
  max_slope_deg: number;
  mean_roughness_tri_m?: number | null;
  estimated_duration_seconds?: number | null;
  gravitational_climb_work_joules?: number | null;
  total_cost: number;
  compute_time_ms: number;
  nodes_expanded: number;
  target_visit_order: string[];
  snap_diagnostics: SnapDiagnostic[];
  simplification_diagnostic: SimplificationDiagnostic;
  science_targets_reached: ScienceStopSummary[];
  corridor_evidence_hits_within_150m: number;
  legs: RouteLegSummary[];
  vertices: RouteVertex[];
  instructions: NavigationInstruction[];
  resolution_suitability: Record<string, ScaleSuitabilityRecord>;
  provenance?: Record<string, unknown> | null;
  limitations: string[];
}

export interface RouteCompareEntry {
  mode: PlanningMode;
  mode_label: string;
  feasible: boolean;
  error_reason?: string | null;
  route?: RouteComputeResponse | null;
}

export interface RouteCompareResponse {
  dataset_id: string;
  source_product_id: string;
  comparison: RouteCompareEntry[];
  comparison_notes: string[];
}

export interface PickedSurfacePoint {
  lat: number;
  lon_east: number;
  elevation_m: number;
  slope_deg?: number | null;
  roughness_tri_m?: number | null;
  dataset_id: string;
}

export interface TerrainPointLookupResponse {
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

export interface SourcesAuditEntry {
  id: string;
  name: string;
  status: string;
  notes?: string;
  reason?: string;
  scale?: string;
  isolated_from_gale_planning?: boolean;
  included_in_mars_pipeline?: boolean;
  layers?: string[];
  endpoints?: string[];
}

export interface SourcesAuditResponse {
  primary_study_region: {
    name: string;
    crs: string;
    bounding_box: { min_lat: number; max_lat: number; min_lon: number; max_lon: number };
  };
  sources: SourcesAuditEntry[];
}

export interface PerseveranceRawImage {
  imageid: string;
  sol: number;
  mission: string;
  site: string;
  isolated_from_gale_planning: boolean;
  camera_instrument?: string | null;
  camera_filter?: string | null;
  title?: string | null;
  caption?: string | null;
  date_taken_utc?: string | null;
  image_url_medium?: string | null;
  image_url_large?: string | null;
  image_url_full_res?: string | null;
}

export interface PerseveranceGalleryResponse {
  status: string;
  mission: string;
  site: string;
  isolated_from_gale_planning: boolean;
  isolation_note: string;
  source_url: string;
  retrieved_at_utc?: string | null;
  total_results: number;
  images: PerseveranceRawImage[];
  error?: string | null;
}

export interface RouteRelativeTelemetry {
  route_id: string;
  nearest_segment_index: number;
  along_track_distance_m: number;
  cross_track_error_m: number;
  remaining_distance_m: number;
  progress_fraction: number;
  corridor_threshold_m: number;
  off_route: boolean;
  heading_deg?: number | null;
  next_waypoint_label?: string | null;
  next_waypoint_lat?: number | null;
  next_waypoint_lon_east?: number | null;
  distance_to_next_waypoint_m?: number | null;
}

export interface TrackingStatusResponse {
  status: "disconnected" | "live" | "stale";
  live_available: boolean;
  message: string;
  is_simulation: boolean;
  ingest_token_configured: boolean;
  provider_id?: string | null;
  session_id?: string | null;
  crs: string;
  sequence_number?: number | null;
  lat?: number | null;
  lon_east?: number | null;
  elevation_m?: number | null;
  horizontal_uncertainty_m?: number | null;
  heading_deg?: number | null;
  fix_timestamp_utc?: string | null;
  age_seconds?: number | null;
  stale_after_seconds?: number | null;
  route_relative?: RouteRelativeTelemetry | null;
}

export interface TrackingReplanPreviewResponse {
  requires_user_confirmation: boolean;
  live_fix_used: {
    provider_id: string;
    sequence_number: number;
    lat: number;
    lon_east: number;
    timestamp_utc: string;
    horizontal_uncertainty_m?: number | null;
  };
  coverage_verified: boolean;
  dem_dataset_id: string;
  dem_source_product_id: string;
  dem_resolution_m: number;
  previous_route_id: string;
  proposed_route: RouteComputeResponse;
  distance_delta_m: number;
  elevation_gain_delta_m: number;
  max_slope_delta_deg: number;
  duration_delta_seconds?: number | null;
  warnings: string[];
  notes: string;
}
