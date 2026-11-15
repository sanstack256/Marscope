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
  acquisition_state?: string | null;
  verification: MetadataVerification;
  failure_reason?: string | null;
  validation_report?: Record<string, unknown> | null;
  raw_product_immutable?: boolean;
  processing_provenance?: Record<string, unknown> | null;
  quality_flags: string[];
  known_limitations: string[];
  processing_history: string[];
  local_file_path?: string | null;
  local_label_path?: string | null;
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

export type InvestigationTargetEvidenceState =
  | "confirmed_local_observation"
  | "orbital_detection_only"
  | "inferred_regional_context_only"
  | "optical_morphology_candidate_unverified"
  | "manual_waypoint_unverified"
  | "data_gap_unassessed"
  | "conflicting_evidence";

export interface ScienceTarget {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  elevation_m?: number | null;
  crs?: string;
  geology_type: string;
  scientific_value?: number | null;
  exploration_priority_score?: number | null;
  scientific_confidence_state?: string | null;
  scientific_confidence_score?: number | null;
  scientific_evidence_summary?: string | null;
  route_utility?: Record<string, unknown> | null;
  prioritization_is_heuristic?: boolean;
  prioritization_label?: string;
  prioritization_breakdown?: Record<string, unknown>;
  instrument_source: string;
  provenance_product_id: string;
  target_status?: TargetProvenanceStatus;
  evidence_state?: InvestigationTargetEvidenceState;
  study_region?: string;
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

export type TextureOverlayMode =
  | "ortho"
  | "elevation"
  | "slope"
  | "roughness"
  | "uncertainty_status"
  | "traversability_state"
  | "observability"
  | "slope_uncertainty_probe";

export type RouteObjective =
  | "SHORTEST_TRAVERSABLE"
  | "LOWEST_SLOPE"
  | "LOWEST_CLIMB_ENERGY"
  | "LOWEST_ROUGHNESS"
  | "HIGHEST_EVIDENCE_COVERAGE"
  | "SCIENCE_CORRIDOR"
  | "BALANCED_MULTIOBJECTIVE";

export interface OverlayLegendDescriptor {
  overlay_id: string;
  label: string;
  available: boolean;
  unavailable_reason?: string | null;
  units: string;
  normalization: string;
  method: string;
  uncertainty_classification: string;
  vmin?: number | null;
  vmax?: number | null;
  no_data_meaning?: string | null;
  palette_stops: Array<{ t: number; rgb?: number[]; hex: string; color?: string }>;
  categories: Array<{ label: string; hex: string }>;
}
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

export type ScientificDataClassification =
  | "DIRECTLY_MEASURED"
  | "ARCHIVE_DERIVED"
  | "MARSCOPE_DERIVED"
  | "MODELLED"
  | "USER_ASSUMED"
  | "UNAVAILABLE"
  | "UNVERIFIED";

export interface ProvenanceStep {
  step_id: string;
  label: string;
  classification: ScientificDataClassification;
  input_ids: string[];
  method: string;
  algorithm_version: string;
  output_variable: string;
  output_units?: string | null;
  output_resolution_m?: number | null;
  parameters: Record<string, unknown>;
  assumptions: string[];
}

export interface ProvenanceDependencyGraph {
  output_id: string;
  classification: ScientificDataClassification;
  input_datasets: string[];
  input_product_ids: string[];
  input_variables: string[];
  input_units: string[];
  input_crs: string;
  input_resolution_m?: number | null;
  input_timestamps: string[];
  method: string;
  algorithm_version: string;
  parameters: Record<string, unknown>;
  assumptions: string[];
  intermediate_steps: ProvenanceStep[];
  output_units?: string | null;
  output_resolution_m?: number | null;
  uncertainty_method: string;
  validation_state: string;
  processing_timestamp: string;
  scientific_notes: string[];
}

export interface MultiScaleMetricEntry {
  metric_name: string;
  value?: number | null;
  units: string;
  classification: ScientificDataClassification;
  physical_radius_m?: number | null;
  actual_window_dimensions_m?: { width_m: number; height_m: number } | null;
  native_resolution_m: number;
  processing_resolution_m: number;
  status: string;
  reason?: string | null;
}

export interface MultiScaleTerrainResponse {
  available: boolean;
  dataset_id?: string | null;
  product_id?: string | null;
  latitude: number;
  longitude_east: number;
  crs: string;
  vertical_datum: string;
  elevation_m?: number | null;
  slope_deg?: number | null;
  aspect_deg?: number | null;
  profile_curvature_inv_m?: number | null;
  planform_curvature_inv_m?: number | null;
  tri_fine_m?: MultiScaleMetricEntry | null;
  tri_medium_m?: MultiScaleMetricEntry | null;
  tpi_m?: MultiScaleMetricEntry | null;
  local_relief_m?: MultiScaleMetricEntry | null;
  valid_coverage_fraction: number;
  unavailable_reason?: string | null;
  provenance_graph?: ProvenanceDependencyGraph | null;
}

export interface OpticalCandidateFeature {
  feature_id: string;
  candidate_type: string;
  latitude: number;
  longitude_east: number;
  score: number;
  edge_magnitude_dn: number;
  local_contrast_zscore: number;
  estimated_diameter_m?: number | null;
  algorithm_version?: string;
  classification: ScientificDataClassification;
  validation_state: string;
  disclaimer: string;
}

export interface OpticalAnalysisResponse {
  available: boolean;
  ortho_dataset_id?: string | null;
  product_id?: string | null;
  bounds: Record<string, number>;
  valid_coverage_fraction: number;
  mean_dn?: number | null;
  std_dn?: number | null;
  mean_sobel_edge_dn?: number | null;
  texture_variance?: number | null;
  candidates: OpticalCandidateFeature[];
  unavailable_reason?: string | null;
  provenance_graph?: ProvenanceDependencyGraph | null;
}

export interface ColorNormalizationStop {
  t: number;
  color: string;
  rgb: number[];
}

export interface ColorNormalizationSpec {
  overlay: string;
  dataset_id: string;
  region_bounds: Record<string, number>;
  processing_version: string;
  scale_type: "sequential" | "source_imagery";
  palette_id: string;
  palette_stops: ColorNormalizationStop[];
  vmin?: number | null;
  vmax?: number | null;
  units?: string | null;
  nodata_label: string;
  nodata_rgba: number[];
  physical_radius_m?: number | null;
  source_resolution_m?: number | null;
  window_dimensions_m?: { width_m: number; height_m: number } | null;
  note?: string | null;
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
  tri_metadata?: Record<string, unknown> | null;
  color_normalizations?: Record<string, ColorNormalizationSpec>;
  overlay_legends?: Record<string, OverlayLegendDescriptor>;
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
  objective?: RouteObjective | null;
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
  provenance_graph?: ProvenanceDependencyGraph | null;
  decision_explainer?: RouteDecisionExplainer | null;
  cost_decomposition?: RouteCostDecomposition | null;
  traversability_summary?: RouteTraversabilitySummary | null;
  uncertainty_status?: string | null;
  limitations: string[];
}

export interface RouteCompareEntry {
  mode: PlanningMode;
  objective?: RouteObjective | null;
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

export type ReadinessState =
  | "ASSESSED"
  | "PARTIALLY_ASSESSED"
  | "INSUFFICIENT_EVIDENCE"
  | "NOT_ASSESSED";

export interface DatasetValidationStage {
  dataset_id: string;
  product_id: string;
  product_type: string;
  catalogued: boolean;
  discovered: boolean;
  acquired: boolean;
  integrity_verified: boolean;
  label_parsed: boolean;
  scientifically_validated: boolean;
  processed: boolean;
  renderable: boolean;
  derived: boolean;
  native_resolution_m?: number | null;
  sha256_checksum?: string | null;
  missing_requirement?: string | null;
}

export interface CorridorPolygon {
  centerline: number[][];
  left_boundary: number[][];
  right_boundary: number[][];
  polygon_ring: number[][];
  clipped_to_dem_footprint: boolean;
  clipped_to_dem_bounds?: boolean;
  corridor_area_m2?: number | null;
  projection: string;
  corridor_width_m: number;
}

export interface TerrainMorphologyCandidate {
  candidate_id: string;
  morphology_type: string;
  segment_id?: string | null;
  latitude: number;
  longitude_east: number;
  footprint_bounds: Record<string, number>;
  detection_method: string;
  input_dataset_id: string;
  input_product_id: string;
  input_resolution_m: number;
  detection_parameters: Record<string, unknown>;
  geometric_measurements: Record<string, number>;
  resolution_status: string;
  classification: string;
  validation_state: string;
  limitations: string[];
  provenance: Record<string, unknown>;
}

export interface RejectedOpticalCandidate {
  feature_id: string;
  latitude: number;
  longitude_east: number;
  rejection_reason: string;
  valid_pixel_fraction: number;
  local_contrast_zscore: number;
}

export interface AssociatedObservation {
  observation_id: string;
  mission: string;
  instrument: string;
  sol?: number | null;
  observation_time?: string | null;
  latitude?: number | null;
  longitude_east?: number | null;
  coordinate_uncertainty_m?: number | null;
  product_id: string;
  distance_from_route_m?: number | null;
  distance_from_corridor_m?: number | null;
  association_type?: string;
  nearest_segment_id?: string | null;
  measurement_type: string;
  availability_status?: string;
  product_available: boolean;
  availability_check_note?: string | null;
  spatial_reference_verified?: boolean;
  is_panorama: boolean;
  classification: string;
  spatial_association_note: string;
}

export interface ResolutionAdequacyRecord {
  analysis_domain: string;
  status: string;
  source_dataset_id?: string | null;
  native_resolution_m?: number | null;
  policy_version: string;
  rationale: string;
}

export interface SegmentCoverageReport {
  segment_id: string;
  dem_coverage_fraction: number;
  valid_elevation_fraction: number;
  slope_available: boolean;
  tri_available: boolean;
  optical_coverage_fraction?: number | null;
  optical_coverage_status?: string;
  optical_footprint_coverage_fraction?: number | null;
  valid_optical_pixel_coverage_fraction?: number | null;
  optical_covered_area_m2?: number | null;
  optical_contributing_product_ids?: string[];
  segment_corridor_area_m2?: number | null;
  dem_valid_area_m2?: number | null;
  optical_quality_note: string;
  geological_map_coverage: boolean;
  geological_map_scale_note: string;
  spectral_data_available: boolean;
  thermal_data_available: boolean;
  rover_observation_count: number;
  panorama_available: boolean;
  source_resolution_m?: number | null;
  unverified_regions_present: boolean;
  validation_status?: string;
  temporal_applicability_note?: string;
}

export interface EvidenceGapCell {
  gap_id: string;
  gap_type: string;
  segment_id?: string | null;
  bounds: Record<string, number>;
  reason: string;
}

export interface CorridorSegmentAssessment {
  segment_id: string;
  segment_index: number;
  start_coord: { lat: number; lon_east: number; label?: string | null };
  end_coord: { lat: number; lon_east: number; label?: string | null };
  vertices?: Array<{ lat: number; lon_east: number; label?: string | null }>;
  corridor_polygon?: number[][];
  corridor_area_m2?: number | null;
  cumulative_start_m?: number | null;
  cumulative_end_m?: number | null;
  geodesic_distance_m: number;
  horizontal_distance_m?: number | null;
  surface_distance_m: number;
  three_d_distance_m?: number | null;
  straight_line_distance_m?: number | null;
  terrain_pixel_count?: number;
  valid_terrain_pixel_count?: number;
  resolution_supportable?: boolean;
  resolution_support_note?: string | null;
  start_elevation_m?: number | null;
  end_elevation_m?: number | null;
  elevation_change_m?: number | null;
  max_slope_deg?: number | null;
  mean_slope_deg?: number | null;
  max_tri_m?: number | null;
  mean_tri_m?: number | null;
  tri_physical_radius_m: number;
  local_relief_m?: number | null;
  mean_profile_curvature_inv_m?: number | null;
  source_dem_id: string;
  source_product_id: string;
  native_resolution_m: number;
  valid_data_coverage_fraction: number;
  uncertainty_summary: string;
  associated_observation_ids: string[];
  optical_candidate_ids: string[];
  morphology_candidate_ids: string[];
  unverified_area_present: boolean;
  coverage: SegmentCoverageReport;
}

export interface CorridorAssessment {
  assessment_id: string;
  dataset_id: string;
  source_product_id: string;
  crs: string;
  local_projection: string;
  corridor_width_m: number;
  segment_scale_m: number;
  observation_search_radius_m: number;
  corridor_geometry: CorridorPolygon;
  route_horizontal_distance_m: number;
  route_surface_distance_m: number;
  segments: CorridorSegmentAssessment[];
  terrain_candidates: TerrainMorphologyCandidate[];
  optical_candidates: OpticalCandidateFeature[];
  rejected_optical_candidates: RejectedOpticalCandidate[];
  observations: AssociatedObservation[];
  coverage_summary: Record<string, unknown>;
  resolution_adequacy: ResolutionAdequacyRecord[];
  evidence_gaps: EvidenceGapCell[];
  uncertainty: {
    dem_vertical_precision_note: string;
    horizontal_resolution_m: number;
    corridor_valid_fraction: number;
    resolution_limited_segments: number;
    nodata_segments: number;
    coordinate_uncertainty_note: string;
    unquantified_limitations: string[];
  };
  dataset_inventory: DatasetValidationStage[];
  compute_time_ms: number;
  cache_validity?: "CURRENT" | "STALE" | "RECOMPUTING" | "FAILED" | "UNAVAILABLE";
  stale_reasons?: string[];
  readiness_policy_version?: string;
  convolution_buffer_m?: number | null;
  convolution_buffer_px?: number | null;
  route_decision_explainer?: RouteDecisionExplainer | null;
}

export interface RouteDecisionExplainer {
  mode: string;
  algorithm: string;
  hard_constraints: Record<string, unknown>;
  soft_cost_weights: Record<string, number>;
  grid_exclusion_summary: Record<string, number>;
  total_cost_breakdown: Record<string, number>;
  dominant_cost_driver: string;
  verified_science_targets_applied: Array<Record<string, unknown>>;
  unverified_optical_candidates_excluded_from_bonus: number;
  sensitivity_notes: string[];
  decision_trace_summary: string;
}

export interface DomainAssessmentRecord {
  domain: string;
  status: string;
  evidence_basis: string;
  policy_version: string;
  threshold_or_rule: string;
  spatial_footprint_coverage_fraction?: number | null;
  valid_measurement_coverage_fraction?: number | null;
  product_availability?: string;
  scientific_validation_state?: string;
  spatial_association_quality?: string;
  resolution_adequacy?: string;
  temporal_relevance?: string;
  missing_inputs?: string[];
  notes: string[];
}

export interface RouteEvidenceComparisonEntry {
  mode: string;
  mode_label: string;
  feasible: boolean;
  error_reason?: string | null;
  assessment_id?: string | null;
  horizontal_distance_m?: number | null;
  surface_distance_m?: number | null;
  elevation_gain_m?: number | null;
  elevation_loss_m?: number | null;
  max_slope_deg?: number | null;
  mean_slope_deg?: number | null;
  max_tri_m?: number | null;
  mean_tri_m?: number | null;
  local_relief_max_m?: number | null;
  terrain_coverage_fraction?: number | null;
  optical_coverage_fraction?: number | null;
  unknown_data_fraction?: number | null;
  resolution_adequacy_status?: string | null;
  associated_observation_count: number;
  science_targets_reached_count: number;
  unresolved_candidate_count: number;
  data_gap_count: number;
  composite_risk_score?: number | null;
  composite_risk_status: string;
}

export interface RouteEvidenceComparisonResponse {
  dataset_id: string;
  source_product_id: string;
  corridor_width_m: number;
  entries: RouteEvidenceComparisonEntry[];
  tradeoff_explanations: string[];
  compute_time_ms: number;
}

export interface PhysicalEnergyBudget {
  available: boolean;
  classification: string;
  input_total_mass_kg?: number | null;
  astronaut_suit_mass_kg?: number | null;
  payload_mass_kg?: number | null;
  surface_weight_n?: number | null;
  mars_gravity_m_s2: number;
  gravity_parameter_source: string;
  gravity_parameter_version: string;
  positive_elevation_gain_m: number;
  negative_elevation_loss_m: number;
  gravitational_pe_increase_j?: number | null;
  gravitational_pe_decrease_j?: number | null;
  net_gravitational_pe_change_j?: number | null;
  disclaimer: string;
  unavailable_reason?: string | null;
}

export interface MissionDossierResponse {
  dossier_id: string;
  mission_name: string;
  study_region: string;
  readiness_state: ReadinessState;
  readiness_reasons: string[];
  missing_inputs: string[];
  corridor_assessment: CorridorAssessment;
  route_comparison?: RouteEvidenceComparisonResponse | null;
  physical_energy_budget: PhysicalEnergyBudget;
  mobility_assessment: Record<string, unknown>;
  scientific_opportunities: Array<Record<string, unknown>>;
  unmodeled_parameters: string[];
  safety_certification_note: string;
  mathematical_assessment_complete?: boolean;
  operational_safety_certified?: boolean;
  domain_assessments?: DomainAssessmentRecord[];
  readiness_policy_version?: string;
  cache_validity?: "CURRENT" | "STALE" | "RECOMPUTING" | "FAILED" | "UNAVAILABLE";
  stale_reasons?: string[];
  corridor_uncertainty_profile?: CorridorUncertaintyProfile | null;
  complementarity_report?: ComplementarityAssessmentReport | null;
}

export interface EvaExplicitResourceSpec {
  resource_name: string;
  category?: string | null;
  initial_quantity: number;
  unit: string;
  consumption_rate: number;
  rate_unit: string;
  reserve_fraction: number;
  source_note?: string | null;
}

export interface EvaResourceEvaluationEntry {
  resource_name: string;
  category?: string | null;
  status: string;
  initial_quantity?: number | null;
  unit: string;
  normalized_rate_per_second?: number | null;
  exposure_duration_s?: number | null;
  reserve_required?: number | null;
  estimated_consumed?: number | null;
  remaining_after_eva?: number | null;
  margin_above_reserve?: number | null;
  equation_applied: string;
  integration_mode?: string;
  reserve_policy_status?: string;
  phase_breakdown?: Record<string, number>;
  assumption_classification?: string;
  explanation: string;
}

export interface ParameterProvenanceRecord {
  parameter_name: string;
  value?: unknown;
  units: string;
  classification: string;
  source_type: string;
  citation?: string | null;
  validity_domain?: string | null;
  confirmed_by_operator: boolean;
  version: string;
}

export interface LocomotionScenarioComparisonEntry {
  scenario_id: string;
  scenario_label: string;
  category: string;
  model_id: string;
  reference_speed_mps?: number | null;
  status: string;
  classification: string;
  outbound_duration_s?: number | null;
  return_duration_s?: number | null;
  total_traverse_duration_s?: number | null;
  mean_effective_speed_mps?: number | null;
  min_effective_speed_mps?: number | null;
  max_effective_speed_mps?: number | null;
  within_mission_duration_limit?: boolean | null;
  disclosure: string;
}

export interface EnvironmentalObservationRecord {
  record_id: string;
  instrument: string;
  mission: string;
  modality: string;
  observation_type: string;
  classification: string;
  location_description: string;
  sol_or_epoch_range: string;
  value?: number | null;
  value_range?: number[] | null;
  unit: string;
  source_citation: string;
  scientific_caveat: string;
}

export interface EvaEnvironmentalContextReport {
  study_region: string;
  live_weather_available: boolean;
  live_weather_status: string;
  live_radiation_available: boolean;
  live_radiation_status: string;
  archive_observations: EnvironmentalObservationRecord[];
  eva_duration_s?: number | null;
  archive_reference_gcr_dose_msv?: number | null;
  archive_reference_gcr_dose_usv?: number | null;
  radiation_calculation_note: string;
  prohibited_inferences: string[];
}

export interface TelemetryConsumableSample {
  channel_name: string;
  value: number;
  unit: string;
}

export interface TelemetryAdapterStatusResponse {
  adapter_name: string;
  adapter_version: string;
  connected: boolean;
  connection_status: string;
  crew_state_status: string;
  freshness_state: string;
  classification: string;
  auth_token_configured: boolean;
  provider_id?: string | null;
  session_id?: string | null;
  sequence_number?: number | null;
  crs?: string | null;
  lat?: number | null;
  lon_east?: number | null;
  elevation_m?: number | null;
  horizontal_uncertainty_m?: number | null;
  heading_deg?: number | null;
  packet_timestamp_utc?: string | null;
  age_seconds?: number | null;
  consumables: TelemetryConsumableSample[];
  rejected_packet_count: number;
  last_rejection_reason?: string | null;
  disclosures: string[];
}

export interface EvaTimeBudgetBreakdown {
  available: boolean;
  outbound_travel_s?: number | null;
  science_stops_s?: number | null;
  operational_overhead_s: number;
  return_travel_s?: number | null;
  reserve_protected_s?: number | null;
  total_required_s?: number | null;
  mission_duration_limit_s?: number | null;
  usable_budget_s?: number | null;
  time_margin_s?: number | null;
  within_time_budget?: boolean | null;
  speed_model_used: string;
  locomotion_category?: string;
  speed_model_validation_note: string;
  locomotion_model?: LocomotionModelSpec | null;
  parameter_provenance?: ParameterProvenanceRecord[];
  missing_inputs: string[];
}

export interface EvaEnergyBudgetBreakdown {
  available: boolean;
  astronaut_suit_mass_kg?: number | null;
  payload_mass_kg?: number | null;
  total_mass_kg?: number | null;
  mars_gravity_m_s2: number | null;
  surface_weight_n?: number | null;
  outbound_climb_gain_m: number;
  outbound_descent_loss_m: number;
  return_climb_gain_m: number;
  return_descent_loss_m: number;
  outbound_climb_work_j?: number | null;
  return_climb_work_j?: number | null;
  total_positive_climb_work_j?: number | null;
  net_gravitational_pe_change_j?: number | null;
  parameter_provenance?: ParameterProvenanceRecord[];
  disclaimer: string;
  missing_inputs: string[];
}

export interface EvaSegmentScheduleItem {
  sequence_index: number;
  leg_role: string;
  segment_id?: string | null;
  label: string;
  start_time_s?: number | null;
  end_time_s?: number | null;
  duration_constant_speed_s?: number | null;
  duration_tobler_approx_s?: number | null;
  distance_m: number;
  elevation_gain_m: number;
  elevation_loss_m: number;
  cumulative_climb_work_j?: number | null;
  vertices: Array<{ lat: number; lon_east: number; label?: string | null }>;
  corridor_polygon: number[][];
  evidence_status: string;
}

export interface EvaReturnPlanReport {
  return_status?:
    | "INDEPENDENT_RETURN_COMPUTED"
    | "RETURN_CONSTRAINTS_UNSATISFIED"
    | "RETURN_COMPUTATION_FAILED"
    | "RETURN_DATA_UNAVAILABLE"
    | "REVERSED_OUTBOUND_REFERENCE_ONLY"
    | "NOT_REQUESTED";
  turnback_ponr_method?: string;
  return_strategy_note?: string;
  overlap_with_outbound_fraction?: number | null;
  locomotion_model?: LocomotionModelSpec | null;
  turnback_checkpoints?: TurnbackCheckpointRecord[];
  return_alternatives?: IndependentReturnAlternative[];
  return_route_computed: boolean;
  return_strategy: string;
  return_route_vertices: Array<{ seq: number; lat: number; lon_east: number; elevation_m: number }>;
  return_horizontal_distance_m: number;
  return_surface_distance_m: number;
  return_elevation_gain_m: number;
  return_elevation_loss_m: number;
  return_duration_constant_s?: number | null;
  return_duration_tobler_s?: number | null;
  asymmetric_climb_delta_m: number;
  return_margin_s?: number | null;
  point_of_no_return_distance_m?: number | null;
  feasible_within_usable_budget?: boolean | null;
  warnings: string[];
}

export interface EvaConstraintCheckRecord {
  constraint_id: string;
  category: string;
  status: string;
  configured_limit?: string | null;
  evaluated_value?: string | null;
  explanation: string;
}

export interface EvaMissionEnvelopeResponse {
  mission_id: string;
  mission_name: string;
  study_region: string;
  dataset_id: string;
  source_product_id: string;
  route_id: string;
  assessment_id: string;
  dossier_id?: string | null;
  envelope_status: string;
  model_feasibility_status?: string;
  workflow_state?: string;
  plan_version?: number;
  stale?: boolean;
  stale_reasons?: string[];
  operational_safety_certified: boolean;
  missing_inputs: string[];
  config?: Record<string, unknown>;
  outbound_summary: Record<string, number>;
  locomotion_model?: LocomotionModelSpec | null;
  locomotion_scenarios?: LocomotionScenarioComparisonEntry[];
  parameter_provenance?: ParameterProvenanceRecord[];
  traversability_analytics?: {
    native_dem_resolution_m?: number;
    minimum_resolvable_feature_width_m?: number;
    unknown_terrain_policy?: string;
    corridor_valid_dem_fraction?: number;
    mean_optical_coverage_fraction?: number | null;
    optical_coverage_status?: string;
    unmeasured_soil_properties?: Record<string, string>;
    sub_pixel_hazard_disclosure?: string;
    [key: string]: unknown;
  };
  time_budget: EvaTimeBudgetBreakdown;
  energy_budget: EvaEnergyBudgetBreakdown;
  resource_budget: {
    overall_status: string;
    entries: EvaResourceEvaluationEntry[];
    category_coverage?: Record<string, string>;
    missing_inputs: string[];
    limitations: string[];
  };
  return_plan: EvaReturnPlanReport;
  schedule: EvaSegmentScheduleItem[];
  constraints: EvaConstraintCheckRecord[];
  environmental_context?: EvaEnvironmentalContextReport | null;
  telemetry_state?: TelemetryAdapterStatusResponse | null;
  uncertainty_notes: string[];
  limitations: string[];
  cache_validity: string;
  compute_time_ms: number;
  linked_campaign_id?: string | null;
  linked_question_id?: string | null;
  integrated_lifecycle_state?: IntegratedMissionLifecycleState | string | null;
}

export interface MissionEventRecord {
  event_id: string;
  mission_id: string;
  event_type: string;
  recorded_at_utc: string;
  operator_id: string;
  description: string;
  payload: Record<string, unknown>;
  invalidated_subsystems: string[];
  triggers_replanning: boolean;
}

export interface PlanComparisonReport {
  comparison_id: string;
  mission_id: string;
  generated_at_utc: string;
  previous_plan_version: number;
  candidate_plan_version: number;
  trigger_event_ids: string[];
  invalidated_subsystems: string[];
  outbound_distance_delta_m: number;
  outbound_climb_gain_delta_m: number;
  return_distance_delta_m: number;
  return_climb_gain_delta_m: number;
  total_mission_time_delta_s?: number | null;
  remaining_time_margin_delta_s?: number | null;
  climb_work_delta_kj?: number | null;
  previous_feasibility_status: string;
  candidate_feasibility_status: string;
  previous_model_feasibility_status: string;
  candidate_model_feasibility_status: string;
  previous_ponr_label?: string | null;
  candidate_ponr_label?: string | null;
  route_overlap_fraction: number;
  geometry_changed: boolean;
  requires_operator_approval: boolean;
  approved_by_operator: boolean;
  summary_notes: string[];
}

export interface MissionVersionHistoryEntry {
  plan_version: number;
  created_at_utc: string;
  status: string;
  reason: string;
  envelope: EvaMissionEnvelopeResponse;
}

export interface MissionOperationalSession {
  mission_id: string;
  workflow_state: string;
  active_plan_version: number;
  active_config: Record<string, unknown>;
  active_envelope: EvaMissionEnvelopeResponse;
  stale: boolean;
  stale_subsystems: string[];
  stale_reasons: string[];
  events: MissionEventRecord[];
  plan_history: MissionVersionHistoryEntry[];
  pending_comparison?: PlanComparisonReport | null;
  linked_campaign_id?: string | null;
  linked_question_id?: string | null;
  integrated_lifecycle_state?: IntegratedMissionLifecycleState | string | null;
}

export interface MissionSensitivityScenarioOutcome {
  scenario_id: string;
  dimension: string;
  scenario_label: string;
  parameter_perturbation: string;
  evaluated: boolean;
  model_feasibility_status: string;
  total_mission_time_s?: number | null;
  remaining_time_margin_s?: number | null;
  within_time_budget?: boolean | null;
  all_resources_within_limit?: boolean | null;
  notes: string;
}

export interface MissionSensitivityAnalysisReport {
  mission_id: string;
  plan_version: number;
  baseline_model_feasibility_status: string;
  stability_classification: string;
  evaluated_scenario_count: number;
  feasible_scenario_count: number;
  infeasible_scenario_count: number;
  unavailable_or_incomplete_count: number;
  scenario_outcomes: MissionSensitivityScenarioOutcome[];
  critical_drivers: string[];
  honest_disclosures: string[];
}

export interface MissionOperationsDossier {
  dossier_id: string;
  dossier_schema_version: string;
  exported_at_utc: string;
  sha256_integrity_digest: string;
  mission_id: string;
  mission_name: string;
  study_region: string;
  workflow_state: string;
  plan_version: number;
  stale: boolean;
  stale_reasons: string[];
  feasibility_status: string;
  model_feasibility_status: string;
  feasibility_summary: string;
  [key: string]: unknown;
}

// ============================================================
// Prompt 16: Terrain Uncertainty, Observability, Complementarity,
// Robust Multi-Route Optimization & Independent Return Analysis
// ============================================================

export interface UncertaintyMetricRecord {
  metric_name: string;
  metric_kind: string;
  status: string;
  value?: number | null;
  units?: string | null;
  confidence_level?: string | null;
  is_spatial_map: boolean;
  is_quantified_empirical_error: boolean;
  source_basis: string;
  notes?: string | null;
}

export interface DatasetUncertaintyProfile {
  model_version: string;
  dataset_id: string;
  product_id: string;
  product_type: string;
  crs: string;
  vertical_datum: string;
  horizontal_resolution_m?: number | null;
  sample_bits?: number | null;
  sample_type?: string | null;
  raw_pds_sample_bits?: number | null;
  raw_pds_sample_type?: string | null;
  processed_raster_dtype?: string | null;
  raw_raster_dtype?: string | null;
  scaling_factor?: number | null;
  scaling_factor_source?: string | null;
  scaling_factor_conflict?: boolean;
  quantization_uncertainty_available?: boolean;
  is_integer_quantized: boolean;
  has_per_pixel_error_raster: boolean;
  pds_keywords_present: Record<string, unknown>;
  elevation_uncertainty_metrics: UncertaintyMetricRecord[];
  overall_elevation_uncertainty_status: string;
  georegistration_uncertainty: Record<string, unknown>;
  missing_uncertainty_fields: string[];
  limitations: string[];
}

export interface SlopeUncertaintySummary {
  status: string;
  metric_kind: string;
  basis_sigma_z_m?: number | null;
  basis_description: string;
  is_empirical_error_map: boolean;
  is_metadata_sensitivity_probe: boolean;
  mean_slope_sigma_deg?: number | null;
  max_slope_sigma_deg?: number | null;
  median_slope_sigma_deg?: number | null;
  near_flat_bias_affected_fraction?: number | null;
  invalid_neighborhood_fraction: number;
  analytical_formula: string;
  notes: string[];
}

export interface RoughnessUncertaintySummary {
  status: string;
  metric_kind: string;
  window_shape_pixels: string;
  window_dimensions_m: Record<string, number>;
  mean_tri_sigma_m?: number | null;
  max_tri_sigma_m?: number | null;
  invalid_neighborhood_fraction: number;
  notes: string[];
}

export interface RegistrationUncertaintyResult {
  dem_dataset_id: string;
  optical_dataset_id?: string | null;
  overall_status: string;
  pair_assessments: Array<Record<string, unknown>>;
  slope_and_point_sensitivity_note: string;
  limitations: string[];
}

export interface FeatureObservabilityRecord {
  category: string;
  observability_state: string;
  source_dataset_id: string;
  native_pixel_scale_m?: number | null;
  minimum_resolvable_feature_size_m?: number | null;
  minimum_recommended_spacing_m?: number | null;
  nyquist_factor_pixels: number;
  policy_id: string;
  policy_version: string;
  classification: string;
  negative_evidence_permitted: boolean;
  negative_evidence_statement: string;
  rationale: string;
}

export interface NegativeEvidenceStatement {
  zero_detections_implies_obstacle_free: boolean;
  unresolved_hazard_classes: string[];
  minimum_resolvable_feature_m?: number | null;
  statement: string;
}

export interface TraversabilityCellBreakdown {
  evaluated_cell_count: number;
  known_exclusion_cell_count: number;
  unknown_insufficient_cell_count: number;
  evaluated_fraction: number;
  known_exclusion_fraction: number;
  unknown_insufficient_fraction: number;
  quantified_uncertainty_cell_fraction: number;
  unquantified_uncertainty_cell_fraction: number;
  traversability_states_present: string[];
}

export interface CorridorUncertaintyProfile {
  model_version: string;
  dataset_profile: DatasetUncertaintyProfile;
  slope_uncertainty: SlopeUncertaintySummary;
  roughness_uncertainty: RoughnessUncertaintySummary;
  registration_uncertainty: RegistrationUncertaintyResult;
  observability: FeatureObservabilityRecord[];
  negative_evidence: NegativeEvidenceStatement;
  traversability_breakdown: TraversabilityCellBreakdown;
  overlay_legends: Record<string, OverlayLegendDescriptor>;
  compute_time_ms: number;
}

export interface DatasetRoleDescriptor {
  dataset_id_pattern: string;
  title: string;
  mission_and_instrument: string;
  native_scale_description: string;
  primary_measurement_domain: string;
  supports: string[];
  does_not_support: string[];
  complementary_role: string;
  isolation_warning?: string | null;
}

export interface CrossValidationRule {
  primary_source: string;
  secondary_source: string;
  relationship: string;
  scientific_caution: string;
}

export interface ComplementarityAssessmentReport {
  registry_id: string;
  registry_version: string;
  active_dataset_ids: string[];
  dataset_roles: DatasetRoleDescriptor[];
  cross_validation_rules: CrossValidationRule[];
  coverage_caveats: string[];
}

export interface RouteCostDecomposition {
  base_distance_cost: number;
  slope_penalty_cost: number;
  uphill_climb_cost: number;
  downhill_descent_cost: number;
  roughness_penalty_cost: number;
  uncertainty_penalty_cost: number;
  nodata_proximity_cost: number;
  science_corridor_reduction: number;
  total_objective_cost: number;
  dominant_cost_driver: string;
  science_bonus_sources_used: string[];
  unverified_optical_candidates_excluded: boolean;
}

export interface RouteTraversabilitySummary {
  evaluated_cell_count: number;
  known_exclusion_cell_count: number;
  unknown_insufficient_cell_count: number;
  evaluated_fraction: number;
  known_exclusion_fraction: number;
  unknown_insufficient_fraction: number;
  unverified_optical_candidates_excluded_from_bonus: boolean;
}

export interface ScenarioSensitivityOutcome {
  scenario_id: string;
  label: string;
  category?:
    | "MEASUREMENT_UNCERTAINTY_PROPAGATION"
    | "MEASUREMENT_SENSITIVITY_ANALYSIS"
    | "ALGORITHM_PARAMETER_SENSITIVITY"
    | "MISSION_ASSUMPTION_SENSITIVITY";
  perturbation_parameter: string;
  perturbation_description: string;
  evaluated?: boolean;
  uncertainty_quantified?: boolean | null;
  route_found: boolean;
  path_changed_from_baseline: boolean;
  path_signature_diff_fraction?: number | null;
  total_distance_m?: number | null;
  estimated_time_s?: number | null;
  max_slope_deg?: number | null;
  total_objective_cost?: number | null;
  constraint_status_changed: boolean;
  notes: string[];
}

export interface RouteSensitivityReport {
  policy_id: string;
  policy_version: string;
  policy_config?: Record<string, unknown>;
  baseline_route_id: string;
  stability_status:
    | "STABLE_ACROSS_EVALUATED_SCENARIOS"
    | "CHANGES_ACROSS_EVALUATED_SCENARIOS"
    | "INSUFFICIENT_SCENARIOS"
    | "NOT_EVALUATED";
  evaluated_scenario_count: number;
  scenarios_where_path_changed: number;
  scenarios_where_infeasible: number;
  dominant_sensitivity_driver?: string | null;
  uncertainty_basis_note: string;
  category_summaries?: Record<string, Record<string, unknown>>;
  scenarios: ScenarioSensitivityOutcome[];
}

export interface DistinctRouteCandidate {
  candidate_id: string;
  objective: RouteObjective;
  objective_label: string;
  diversification_method: string;
  max_overlap_with_prior_routes: number;
  route: RouteComputeResponse;
  return_computed: boolean;
  return_status?: string | null;
  return_distance_m?: number | null;
  return_elevation_gain_m?: number | null;
  return_overlap_with_outbound_fraction?: number | null;
  sensitivity_summary?: RouteSensitivityReport | null;
  evidence_highlights: string[];
}

export interface RobustRouteCompareResponse {
  dataset_id: string;
  source_product_id: string;
  alternative_generation_status:
    | "DISTINCT_ALTERNATIVES_AVAILABLE"
    | "SINGLE_CORRIDOR_BOTTLENECK"
    | "INSUFFICIENT_FEASIBLE_ROUTES";
  search_algorithm?: string;
  diversification_strategy?: string;
  search_limits?: Record<string, unknown>;
  overlap_metric_definition?: string;
  global_optimality_disclaimer?: string;
  recommended_candidate_id?: string | null;
  recommendation_rationale: string;
  distinct_candidate_count: number;
  duplicate_candidates_rejected: number;
  pairwise_overlap_matrix: Record<string, Record<string, number>>;
  candidates: DistinctRouteCandidate[];
  rejected_near_duplicates: Array<Record<string, unknown>>;
  rejected_candidates?: Array<Record<string, unknown>>;
  failure_reasons?: string[];
  limitations: string[];
  stage_timings_ms?: Record<string, number>;
  compute_time_ms: number;
}

export interface LocomotionModelSpec {
  model_id: string;
  model_version: string;
  category?: string;
  classification: string;
  description: string;
  applicable_scope: string;
  unvalidated_note: string;
  min_valid_slope_deg?: number;
  max_valid_slope_deg?: number;
}

export interface TurnbackCheckpointRecord {
  checkpoint_index: number;
  lat: number;
  lon_east: number;
  outbound_distance_m: number;
  outbound_elapsed_s?: number | null;
  return_route_computed: boolean;
  independent_return_distance_m?: number | null;
  independent_return_elevation_gain_m?: number | null;
  independent_return_duration_constant_s?: number | null;
  independent_return_duration_tobler_s?: number | null;
  estimated_roundtrip_time_s?: number | null;
  fits_usable_budget?: boolean | null;
  return_differs_from_outbound: boolean;
  failure_reason?: string | null;
}

export interface IndependentReturnAlternative {
  alternative_id: string;
  objective: RouteObjective;
  strategy_label: string;
  horizontal_distance_m: number;
  surface_distance_m: number;
  elevation_gain_m: number;
  max_slope_deg: number;
  mean_slope_deg: number;
  estimated_time_constant_s?: number | null;
  estimated_time_tobler_s?: number | null;
  spatial_overlap_with_primary_fraction: number;
  overlap_with_outbound_fraction: number;
  vertices: RouteVertex[];
}


// ============================================================
// PROMPT 17 — SCIENCE CAMPAIGN, INSTRUMENT CAPABILITIES & OBSERVATION COMPARISON
// ============================================================

export type InstrumentPlatformKind = "orbital" | "surface_in_situ";

export type MeasurementClass =
  | "mineralogy_spectral"
  | "mineralogy_xrd"
  | "elemental_chemistry"
  | "volatile_organic_isotope"
  | "morphology_highres"
  | "topography_elevation"
  | "thermal_inertia_composition"
  | "hydrated_neutron_subsurface"
  | "meteorology_environment";

export type RequirementFulfillmentState =
  | "satisfied_direct"
  | "satisfied_proxy_only"
  | "partial_coverage_or_resolution_limited"
  | "missing_required_data"
  | "conflict_requires_resolution"
  | "cannot_be_verified_with_available_archive";

export type EvidenceMatchStrength =
  | "direct_local_in_situ"
  | "orbital_footprint_intersection"
  | "context_only_scale_mismatch"
  | "unverified_optical_only"
  | "absent_data_gap"
  | "mission_isolated_rejected";

export type CampaignFreshnessState =
  | "current"
  | "stale_upstream_dependency_changed";

export type CampaignPlanStatus =
  | "complete_constrained_plan"
  | "partial_missing_observations"
  | "infeasible_under_constraints"
  | "data_insufficient";

export type ArchiveComparisonOutcome =
  | "consistent_with_archive"
  | "extends_archive_coverage"
  | "differs_from_prior_local_measurement"
  | "differs_from_orbital_scale_expectation"
  | "conflict_unresolved"
  | "no_co_located_archive_for_comparison";

export interface InstrumentCapabilityRecord {
  instrument_id: string;
  instrument_name: string;
  mission_host: string;
  study_region_scope: string;
  platform_kind: InstrumentPlatformKind;
  measurement_class: MeasurementClass;
  typical_spatial_scale_m?: number | null;
  registry_entry_id?: string;
  registry_version?: string;
  verification_status?: string;
  measurement_modality?: string;
  physical_quantity_measured?: string;
  measurement_method?: string;
  unresolved_fields?: string[];
  source_references?: Array<Record<string, string>>;
  measured_observables: string[];
  allowed_inferences: string[];
  prohibited_inferences: string[];
  mission_isolated_from_gale: boolean;
  mission_isolation_note?: string | null;
}

export interface InferenceValidationRequest {
  instrument_id: string;
  claimed_inference: string;
}

export interface InferenceValidationResponse {
  instrument_id: string;
  claimed_inference: string;
  allowed: boolean;
  classification: string;
  rationale: string;
  prohibited_inferences: string[];
}

export interface MeasurementRequirementSpec {
  requirement_id: string;
  label: string;
  measurement_class: MeasurementClass;
  required_observables: string[];
  allowed_instrument_ids: string[];
  prohibited_substitutions: string[];
  essential: boolean;
  minimum_spatial_resolution_m?: number | null;
  justification: string;
}

export interface ScienceQuestionDefinition {
  question_id: string;
  title: string;
  study_region: string;
  hypothesis: string;
  geological_setting: string;
  is_user_defined: boolean;
  target_phenomena: string[];
  required_measurement_specs: MeasurementRequirementSpec[];
  preferred_stop_count: number;
  minimum_evidence_note: string;
  competing_hypotheses?: string[];
  alternative_explanations?: string[];
  contradicting_evidence_criteria?: string[];
  unresolved_assumptions?: string[];
  current_evidence_state?: string;
  created_at_utc: string;
}

export interface CustomScienceQuestionCreateRequest {
  title: string;
  study_region?: string;
  hypothesis: string;
  geological_setting?: string;
  target_phenomena?: string[];
  required_measurement_classes?: MeasurementClass[];
  preferred_stop_count?: number;
}

export interface RequirementEvaluationRecord {
  requirement_id: string;
  label: string;
  measurement_class: MeasurementClass;
  essential: boolean;
  fulfillment_state: RequirementFulfillmentState;
  canonical_state?: string;
  required_measurement?: string[];
  required_spatial_scale_m?: number | null;
  threshold_rule_classification?: string | null;
  threshold_rationale?: string | null;
  evidence_eligibility_summary?: Record<string, number>;
  coverage_status?: string;
  quality_status?: string;
  missing_information?: string[];
  failure_reason?: string | null;
  resolution_path?: string[];
  satisfying_source_ids: string[];
  satisfying_instruments: string[];
  matched_evidence_count: number;
  limitations_and_gaps: string[];
  prohibited_substitutions: string[];
}

export interface EvidenceMatchRecord {
  match_id: string;
  source_type: string;
  source_id: string;
  product_id?: string | null;
  instrument_id: string;
  mission_host: string;
  study_region: string;
  dataset_status: string;
  eligibility_state?: string;
  eligibility_dimensions?: EvidenceEligibilityDimensionRecord[];
  evidence_role?: string;
  evidence_role_rationale?: string | null;
  scientific_relevance?: string;
  evidence_strength: EvidenceMatchStrength;
  spatial_scale_m?: number | null;
  product_spatial_resolution_m?: number | null;
  product_footprint_bounds?: Record<string, number> | null;
  processing_level?: string | null;
  coordinate_reference?: string | null;
  units?: string | null;
  calibration_status?: string | null;
  integrity_status?: string | null;
  spatial_registration_state?: string;
  product_limitations?: string[];
  uncertainty_summary?: Record<string, unknown>;
  duplication_or_correlation?: Record<string, unknown> | null;
  provenance_chain?: string[];
  matched_observables: string[];
  scale_mismatch_warning?: string | null;
  prohibited_inference_guard?: string | null;
  rejected_for_gale_reason?: string | null;
  citation?: string | null;
}

export interface QuestionEvidenceDiscoveryResponse {
  question: ScienceQuestionDefinition;
  matched_records: EvidenceMatchRecord[];
  isolated_or_rejected_records: EvidenceMatchRecord[];
  requirements_evaluation: RequirementEvaluationRecord[];
  overall_evidence_readiness: string;
  critical_data_gaps: string[];
  evidence_synthesis?: EvidenceSynthesisSummary | null;
  spatial_registrations?: Array<Record<string, unknown>>;
  provenance_graph?: ScienceProvenanceGraph | null;
  discovered_at_utc: string;
}

export interface TargetEvaluationRequest {
  question_id?: string;
  target_ids?: string[];
  include_discovered_candidates?: boolean;
  astronaut_latitude?: number | null;
  astronaut_longitude?: number | null;
  search_radius_m?: number;
  max_candidates?: number;
  study_bounds?: Record<string, number> | null;
}

export interface CandidateTargetEvaluation {
  target_id: string;
  name: string;
  latitude: number;
  longitude_east: number;
  elevation_m?: number | null;
  crs: string;
  evidence_state: InvestigationTargetEvidenceState;
  study_region: string;
  matched_species?: string | null;
  distinct_instruments: string[];
  local_observation_count: number;
  nearest_observation_distance_m?: number | null;
  covering_datasets: string[];
  known_facts: string[];
  inferred_context: string[];
  unknowns_and_gaps: string[];
  conflicting_records: string[];
  heuristic_priority_score: number | null;
  exploration_priority?: number | null;
  scientific_evidence_summary?: Record<string, unknown> | null;
  scientific_relevance?: string;
  route_utility?: Record<string, unknown> | null;
  scientific_confidence_state?: string;
  scientific_confidence_score?: number | null;
  evidence_eligibility_states?: string[];
  spatial_registration_state?: string;
  uncertainty_notes?: string[];
  eligibility_decision?: string;
  eligibility_decision_rationale?: string;
  prioritization_is_heuristic: boolean;
  prioritization_breakdown: Record<string, unknown>;
  eligibility_for_sampling: string;
  prohibited_inference_flags: string[];
  evidence_ids: string[];
  spatial_registration_detail?: Record<string, unknown> | null;
  terrain_elevation_m?: number | null;
  terrain_slope_deg?: number | null;
  terrain_roughness_tri_m?: number | null;
  terrain_data_classification?: string | null;
  spatial_coverage_category?: string | null;
  morphology_candidate_ids?: string[];
  morphology_review_status?: string | null;
}

export type IntegratedMissionLifecycleState =
  | "SCIENTIFIC_QUESTION"
  | "MEASUREMENT_REQUIREMENTS"
  | "EVIDENCE_DISCOVERY"
  | "EVIDENCE_ASSESSMENT"
  | "TARGET_EVALUATION"
  | "CAMPAIGN_DESIGN"
  | "OBSERVATION_PLAN"
  | "SPATIAL_ASSESSMENT"
  | "MOBILITY_ASSESSMENT"
  | "EVA_OPERATIONAL_EVALUATION"
  | "MISSION_REVIEW"
  | "OPERATOR_APPROVAL"
  | "EXECUTION_NOT_STARTED"
  | "FIELD_OBSERVATION"
  | "EVIDENCE_UPDATE"
  | "HYPOTHESIS_REASSESSMENT"
  | "CAMPAIGN_FRESHNESS_CHECK"
  | "REPLAN_IF_REQUIRED";

export type ObservationLifecycleState =
  | "CAPABILITY_DOCUMENTED"
  | "PRODUCT_AVAILABLE"
  | "SPATIALLY_CO_REGISTERED"
  | "OBSERVATION_PLANNED"
  | "OBSERVATION_RECORDED"
  | "EVIDENCE_VALIDATED"
  | "ARCHIVE_COMPARED"
  | "MEASUREMENT_NOT_SUPPORTED";

export interface LifecycleTransitionRecord {
  transition_id: string;
  from_state?: string | null;
  to_state: string;
  trigger: string;
  actor: string;
  timestamp_utc: string;
  detail: string;
  linked_event_id?: string | null;
  plan_version?: number | null;
}

export interface HypothesisReassessmentRecord {
  reassessment_id: string;
  observation_id: string;
  comparison_id: string;
  target_id?: string | null;
  outcome: string;
  previous_target_state?: string | null;
  updated_target_state?: string | null;
  hypothesis_impact: string;
  triggers_replan: boolean;
  recorded_at_utc: string;
}

export interface LinkedInvalidationEvent {
  invalidation_id: string;
  source_subsystem: string;
  event_type: string;
  severity: string;
  detail: string;
  affected_ids: string[];
  recorded_at_utc: string;
  acknowledged: boolean;
}

export interface MissionLifecycleSummaryResponse {
  campaign_id: string;
  campaign_name: string;
  question_id: string;
  dataset_id: string;
  linked_mission_id?: string | null;
  plan_version: number;
  integrated_lifecycle_state: IntegratedMissionLifecycleState | string;
  operator_approved: boolean;
  operator_approved_by?: string | null;
  freshness: CampaignFreshnessReport;
  eva_session?: {
    mission_id: string;
    workflow_state: string;
    active_plan_version: number;
    stale: boolean;
    stale_reasons: string[];
    events_count: number;
    pending_replan: boolean;
  } | null;
  stop_observation_states: Array<{
    stop_id: string;
    target_id: string;
    observation_lifecycle_state: string;
    platform_compatibility: string;
    platform_mismatch_disclosed: boolean;
  }>;
  hypothesis_reassessments: HypothesisReassessmentRecord[];
  lifecycle_transitions: LifecycleTransitionRecord[];
  linked_invalidation_events: LinkedInvalidationEvent[];
}

export interface TargetEvaluationBatchResponse {
  question_id: string;
  evaluated_at_utc: string;
  targets: CandidateTargetEvaluation[];
  rejected_targets?: CandidateTargetEvaluation[];
  state_counts: Record<string, number>;
  prioritization_disclaimer: string;
}

export interface ObservationActionPlan {
  stop_id: string;
  target_id: string;
  target_name: string;
  recommended_instruments: string[];
  measurements_to_collect: string[];
  context_imaging_checks: string[];
  calibration_or_reference_checks: string[];
  expected_dwell_s: number;
  estimated_data_volume_mb: number | null;
  data_volume_status?: string;
  observation_lifecycle_state?: ObservationLifecycleState | string;
  platform_compatibility?: string;
  platform_mismatch_disclosed?: boolean;
  platform_disclosure_note?: string;
  explicit_uncertainty_notes: string[];
  prohibited_shortcut_notes: string[];
}

export interface SamplingProtocolSpec {
  stop_id: string;
  target_id: string;
  sample_type: string;
  eligibility_state: string;
  scientific_rationale: string;
  required_pre_sample_measurements: string[];
  contamination_controls: string[];
  sample_preservation_notes: string[];
  prohibited_without_evidence: boolean;
}

export interface CampaignStopPlan {
  stop_index: number;
  stop_id: string;
  target_id: string;
  name: string;
  latitude: number;
  longitude_east: number;
  evidence_state: InvestigationTargetEvidenceState;
  dwell_s: number;
  heuristic_priority_score: number | null;
  known_summary: string[];
  unknown_summary: string[];
  observation_plan: ObservationActionPlan;
  sampling_protocol: SamplingProtocolSpec;
}

export interface CampaignRouteCandidate {
  alternative_id: string;
  label: string;
  objective: string;
  routing_mode: PlanningMode;
  stop_order_ids: string[];
  outbound_route_id?: string | null;
  outbound_distance_m?: number | null;
  outbound_elevation_gain_m?: number | null;
  max_slope_deg?: number | null;
  outbound_duration_s?: number | null;
  science_dwell_s: number;
  return_route_computed: boolean;
  return_distance_m?: number | null;
  return_duration_s?: number | null;
  total_duration_s?: number | null;
  total_climb_work_j?: number | null;
  feasible_within_constraints?: boolean | null;
  scientific_coverage_summary: string;
  explanation: string;
  failure_reason?: string | null;
}

export interface CampaignBuildRequest {
  campaign_id?: string | null;
  campaign_name?: string;
  question_id?: string;
  dataset_id?: string;
  start: RouteCoordinateInput;
  destination?: RouteCoordinateInput | null;
  selected_target_ids?: string[];
  candidate_targets?: CandidateTargetEvaluation[];
  routing_mode?: PlanningMode;
  constraints?: Partial<RoutePlanningConstraints> | null;
  walking_speed_mps?: number | null;
  use_tobler_grade_approximation?: boolean;
  mission_duration_limit_s?: number | null;
  return_reserve_fraction?: number | null;
  operational_overhead_s?: number;
  stop_dwell_seconds?: Record<string, number>;
  default_stop_dwell_s?: number;
  astronaut_suit_mass_kg?: number | null;
  payload_mass_kg?: number | null;
  resources?: EvaExplicitResourceSpec[];
  include_alternatives?: boolean;
  optimize_stop_order?: boolean;
  locomotion_category?: string;
  unknown_terrain_policy?: string;
  operator_unknown_override_reason?: string | null;
  confirm_default_policies?: boolean;
  expected_plan_version?: number | null;
}

export interface CampaignSummary {
  campaign_id: string;
  campaign_name: string;
  question_id: string;
  dataset_id: string;
  linked_mission_id?: string | null;
  plan_version?: number;
  integrated_lifecycle_state?: IntegratedMissionLifecycleState | string;
  operator_approved?: boolean;
  plan_status: CampaignPlanStatus;
  feasibility_state?: string;
  freshness_state: CampaignFreshnessState;
  stop_count: number;
  total_distance_m?: number | null;
  total_duration_s?: number | null;
  created_at_utc: string;
}

export interface CampaignFreshnessReport {
  campaign_id: string;
  freshness_state: CampaignFreshnessState;
  stored_signature: string;
  current_signature: string;
  staleness_reasons: string[];
  checked_at_utc: string;
}

export interface ScienceCampaignPlan {
  campaign_id: string;
  campaign_name: string;
  question: ScienceQuestionDefinition;
  dataset_id: string;
  study_region: string;
  plan_status: CampaignPlanStatus;
  feasibility_state?: string;
  evaluated_inputs_and_constraints?: Record<string, unknown>;
  epistemic_classification?: Record<string, string[]>;
  constraint_evaluation_complete?: boolean;
  survivability_disclaimer?: string;
  freshness_state: CampaignFreshnessState;
  staleness_reasons: string[];
  dependency_signature: string;
  dependency_snapshot: Record<string, unknown>;
  operational_safety_certified: boolean;
  request: CampaignBuildRequest;
  requirements_evaluation: RequirementEvaluationRecord[];
  stop_plans: CampaignStopPlan[];
  outbound_route_id?: string | null;
  outbound_route_summary: Record<string, unknown>;
  outbound_vertices: Array<{
    lat: number;
    lon_east: number;
    elevation_m?: number | null;
    slope_deg?: number | null;
  }>;
  return_plan?: EvaReturnPlanReport | null;
  eva_envelope?: EvaMissionEnvelopeResponse | null;
  alternatives: CampaignRouteCandidate[];
  missing_inputs: string[];
  uncertainty_and_gaps: string[];
  decision_justification: string[];
  provenance_graph: ProvenanceDependencyGraph;
  data_classification: ScientificDataClassification;
  linked_mission_id?: string | null;
  plan_version?: number;
  integrated_lifecycle_state?: IntegratedMissionLifecycleState | string;
  operator_approved?: boolean;
  operator_approved_by?: string | null;
  operator_approved_at_utc?: string | null;
  operator_approval_note?: string | null;
  hypothesis_reassessments?: HypothesisReassessmentRecord[];
  lifecycle_transitions?: LifecycleTransitionRecord[];
  linked_invalidation_events?: LinkedInvalidationEvent[];
  created_at_utc: string;
  compute_time_ms: number;
}

export interface RecordObservationRequest {
  campaign_id?: string | null;
  stop_id?: string | null;
  target_id?: string | null;
  instrument_id: string;
  measurement_type: string;
  species_or_feature: string;
  measured_value: unknown;
  units?: string;
  latitude: number;
  longitude_east: number;
  coordinate_reference?: string;
  observer_identity?: string;
  calibration_metadata?: string | null;
  raw_attachment_ref?: string | null;
  client_submission_id?: string | null;
  expected_plan_version?: number | null;
  sol_or_timestamp?: string | null;
  notes?: string | null;
  measurement_scale_m?: number | null;
  quality_flag?: string;
}

export interface RecordedFieldObservation {
  observation_id: string;
  campaign_id?: string | null;
  stop_id?: string | null;
  target_id?: string | null;
  instrument_id: string;
  measurement_type: string;
  species_or_feature: string;
  measured_value: unknown;
  units: string;
  latitude: number;
  longitude_east: number;
  coordinate_reference?: string;
  observer_identity?: string;
  calibration_metadata?: string | null;
  raw_attachment_ref?: string | null;
  client_submission_id?: string | null;
  validation_state?: string;
  lifecycle_state?: ObservationLifecycleState | string;
  reassessment_impact?: string | null;
  sol_or_timestamp?: string | null;
  notes?: string | null;
  measurement_scale_m?: number | null;
  quality_flag: string;
  prohibited_inference_warning?: string | null;
  recorded_at_utc: string;
}

export interface ObservationArchiveComparison {
  comparison_id: string;
  observation_id: string;
  outcome: ArchiveComparisonOutcome;
  search_radius_m: number;
  same_scale_archive_records: Array<Record<string, unknown>>;
  orbital_context_records: Array<Record<string, unknown>>;
  scale_disparity_notes: string[];
  value_comparison_summary: Record<string, unknown>;
  explanation: string;
  next_verification_steps: string[];
  compared_at_utc: string;
}

export interface IngestionLedgerResponse {
  acquisition_ledger: Array<Record<string, unknown>>;
  query_provenance: Array<Record<string, unknown>>;
}

export interface EvidenceEligibilityDimensionRecord {
  dimension: string;
  status: string;
  detail: string;
  source_reference?: string | null;
}

export interface EvidenceSynthesisSummary {
  total_records_inspected: number;
  eligible_direct_count: number;
  eligible_supporting_count: number;
  limited_or_indirect_count: number;
  contradicting_count: number;
  inconclusive_count: number;
  ineligible_or_rejected_count: number;
  duplicate_count: number;
  independent_record_count: number;
  has_contradictions: boolean;
  unresolved_gaps: string[];
  synthesis_notes: string[];
}

export interface ProvenanceGraphNode {
  node_id: string;
  node_type: string;
  label: string;
  status?: string | null;
  checksum_sha256?: string | null;
  metadata?: Record<string, unknown>;
}

export interface ProvenanceGraphEdge {
  source_id: string;
  target_id: string;
  relationship: string;
  notes?: string | null;
}

export interface ScienceProvenanceGraph {
  graph_version?: string;
  root_entity_id?: string | null;
  nodes: ProvenanceGraphNode[];
  edges: ProvenanceGraphEdge[];
  generated_at_utc?: string;
}

export interface ProductDetailInspectionResponse {
  dataset: Dataset;
  classified_instrument: string;
  question_id: string;
  eligibility_state: string;
  evidence_role: string;
  evidence_role_rationale: string;
  scientific_relevance: string;
  eligibility_dimensions: EvidenceEligibilityDimensionRecord[];
  spatial_registration_state: string;
  spatial_registration_report: Record<string, unknown>;
  uncertainty_summary: Record<string, unknown>;
  provenance_chain: string[];
}

export interface CampaignDossierExport {
  dossier_version: string;
  exported_at_utc: string;
  operational_safety_certified: boolean;
  campaign: Record<string, unknown>;
  freshness: Record<string, unknown>;
  evidence_discovery: Record<string, unknown>;
  recorded_field_observations: Array<Record<string, unknown>>;
  archive_comparisons: Array<Record<string, unknown>>;
}

// --- Prompt 19: High-Fidelity Multi-Mission Spatial Intelligence Types ---

export interface CrsValidationResult {
  input_crs: string | null;
  canonical_identifier: string | null;
  valid: boolean;
  validation_state: string;
  crs_category: string;
  planetary_body: string;
  shape_type: string | null;
  semi_major_axis_m: number | null;
  semi_minor_axis_m: number | null;
  latitude_convention: string;
  longitude_convention: string;
  vertical_reference: string;
  is_projected: boolean;
  blockers: string[];
  warnings: string[];
  limitations: string[];
  verified_event_method: string | null;
  verified_at_utc: string | null;
}

export interface VerticalDatumComparisonResult {
  compatible: boolean;
  validation_state: string;
  datum_a: string;
  datum_b: string;
  is_absolute_elevation_a: boolean;
  is_absolute_elevation_b: boolean;
  requires_validated_transformation: boolean;
  explanation: string;
  warnings: string[];
}

export interface CoordinateTransformationResult {
  success: boolean;
  validation_state: string;
  source_crs: string;
  target_crs: string;
  algorithm: string;
  library: string;
  library_version: string;
  input_coordinates: Record<string, number>;
  output_coordinates: Record<string, number> | null;
  axis_order: string;
  longitude_normalization: string;
  latitude_convention_in: string;
  latitude_convention_out: string;
  ellipsoid_assumptions: string;
  vertical_reference_in: string;
  vertical_reference_out: string;
  vertical_compatible: boolean;
  known_error_or_limitation: string | null;
  failure_reason: string | null;
  provenance_steps: string[];
}

export interface GeoJsonGeometry {
  type: string;
  coordinates: unknown;
}

export interface SpatialFootprintRecord {
  dataset_id: string;
  product_id: string;
  mission: string;
  instrument: string;
  category: string;
  crs: string;
  coordinate_validation: CrsValidationResult;
  extraction_method: string;
  is_approximate: boolean;
  geometry_valid: boolean;
  repair_applied: boolean;
  antimeridian_split: boolean;
  original_bounds: Record<string, number> | null;
  footprint_geojson: GeoJsonGeometry | null;
  valid_data_geojson: GeoJsonGeometry | null;
  invalid_nodata_geojson: GeoJsonGeometry | null;
  product_footprint_area_m2: number | null;
  valid_data_area_m2: number | null;
  invalid_nodata_area_m2: number | null;
  valid_data_fraction: number | null;
  bbox_area_m2: number | null;
  swath_to_bbox_ratio: number | null;
  area_calculation_method: string;
  horizontal_resolution_m: number | null;
  vertical_resolution_m: number | null;
  pixel_grid_shape: number[] | null;
  data_quality_coverage: string;
  has_local_artifact: boolean;
  source_sha256: string | null;
  processing_history: string[];
  limitations: string[];
  classification: string;
}

export interface PixelAlignmentMetrics {
  evaluated_locally: boolean;
  crs_exact_string_match: boolean;
  transform_origin_offset_m: number | null;
  subpixel_phase_offset_px: number | null;
  resolution_a_m: number | null;
  resolution_b_m: number | null;
  resolution_ratio: number | null;
  grid_alignment_status: string;
  note: string;
}

export interface RegistrationMethodExecution {
  method_name: string;
  algorithm: string;
  input_data: string;
  control_points_count: number;
  valid_correspondences: number;
  rejected_correspondences: number;
  residual_error_px: number | null;
  residual_error_m: number | null;
  spatial_distribution_of_residuals: string | null;
  transformation_model: string | null;
  validation_result: string;
  failure_reason: string | null;
}

export interface RegistrationUncertaintyBreakdown {
  source_geolocation_uncertainty_a_m: number | null;
  source_geolocation_uncertainty_b_m: number | null;
  control_point_uncertainty_m: number | null;
  transformation_residual_m: number | null;
  pixel_quantization_half_px_a_m: number | null;
  pixel_quantization_half_px_b_m: number | null;
  resampling_effect_note: string | null;
  relative_alignment_uncertainty_m: number | null;
  independence_assumption_valid: boolean;
  independence_rationale: string;
  total_uncertainty_computable: boolean;
  uncertainty_gap_reason: string | null;
}

export interface RegistrationStepTrace {
  step_number: number;
  step_name: string;
  status: string;
  detail: string;
}

export interface SpatialRegistrationAssessment {
  assessment_version: string;
  crs_registry_version: string;
  dataset_a_id: string;
  dataset_b_id: string;
  product_a_id: string;
  product_b_id: string;
  intended_analysis: string;
  overall_state: string;
  suitable_for_intended_analysis: boolean;
  crs_compatible: boolean;
  crs_a_validation: CrsValidationResult;
  crs_b_validation: CrsValidationResult;
  vertical_datum_comparison: VerticalDatumComparisonResult | null;
  footprint_overlap_status: string;
  overlap_area_m2: number | null;
  overlap_fraction_of_a: number | null;
  overlap_fraction_of_b: number | null;
  bbox_overlapped_while_valid_pixels_disjoint: boolean;
  pixel_alignment: PixelAlignmentMetrics;
  resolution_compatibility: string;
  temporal_compatibility: string;
  absolute_geolocation_accuracy: string;
  relative_registration_accuracy: string;
  registration_methods_attempted: RegistrationMethodExecution[];
  uncertainty_breakdown: RegistrationUncertaintyBreakdown;
  workflow_steps: RegistrationStepTrace[];
  limitations: string[];
  required_corrective_actions: string[];
  classification: string;
}

export interface CategorySpatialCoverage {
  category: string;
  matching_product_ids: string[];
  local_verified_product_ids: string[];
  best_native_resolution_m: number | null;
  study_area_m2: number;
  product_footprint_area_m2: number;
  valid_pixel_area_m2: number;
  calibrated_data_area_m2: number;
  spatially_registered_area_m2: number;
  scientifically_eligible_area_m2: number;
  product_footprint_fraction: number | null;
  valid_pixel_fraction: number | null;
  calibrated_data_fraction: number | null;
  spatially_registered_fraction: number | null;
  scientifically_eligible_fraction: number | null;
  has_approximate_footprints: boolean;
  only_approximate_footprints: boolean;
  percentage_reporting_policy: string;
  rover_point_observation_count: number;
  footprint_union_geojson: GeoJsonGeometry | null;
  valid_pixel_union_geojson: GeoJsonGeometry | null;
  limitations: string[];
}

export interface SpatialGapRegion {
  gap_id: string;
  category: string;
  gap_cause: string;
  area_m2: number;
  area_fraction_of_study_region: number;
  contributing_product_ids: string[];
  summary: string;
  never_implies_feature_absence: boolean;
  interpretation_warning: string;
  recommended_action: string;
  geometry_geojson: GeoJsonGeometry | null;
}

export interface MultiCategorySpatialCoverageReport {
  study_bounds: Record<string, number>;
  study_area_m2: number;
  area_calculation_method: string;
  reference_dataset_id: string | null;
  intended_resolution_threshold_m: number;
  question_focus: string | null;
  categories: Record<string, CategorySpatialCoverage>;
  evidence_gaps: SpatialGapRegion[];
  overall_limitations: string[];
  classification: string;
}

export interface NativeDemMetadataRecord {
  dataset_id: string;
  product_id: string;
  native_pixel_spacing_m: number | null;
  horizontal_crs: string;
  crs_validation: CrsValidationResult;
  vertical_datum: string;
  vertical_datum_description: string;
  elevation_units: string;
  nodata_value: number | null;
  source_uncertainty_vertical_m: number | null;
  pixel_registration: string;
  processing_level: string;
  source_provenance: string;
  source_sha256: string | null;
  raster_dimensions: number[] | null;
  has_overviews: boolean;
  overview_factors: number[];
}

export interface TerrainScaleObservabilityReport {
  dataset_id: string;
  native_resolution_m: number | null;
  nyquist_resolvable_feature_m: number | null;
  min_3x3_slope_baseline_m: number | null;
  resolvable_features: string[];
  below_effective_resolution: string[];
  noise_or_interpolation_affected: string[];
  unavailable_due_to_nodata_or_resolution: string[];
  unknown_terrain_policy: string;
  coarse_absence_policy: string;
}

export interface TerrainDerivativeMetadata {
  derivative_name: string;
  available: boolean;
  valid_reason: string | null;
  input_dem_id: string;
  input_product_id: string;
  native_resolution_m: number;
  processing_resolution_m: number;
  resampling_applied: boolean;
  resampling_method: string | null;
  window_or_physical_scale: string;
  algorithm: string;
  algorithm_version: string;
  edge_treatment: string;
  nodata_handling: string;
  units: string;
  uncertainty_treatment: string;
  processing_provenance: string[];
  stats: Record<string, number | null>;
}

export interface WindowedTerrainDerivativesReport {
  dataset_metadata: NativeDemMetadataRecord;
  requested_bounds: Record<string, number>;
  grid_shape: number[];
  valid_pixel_count: number;
  nodata_pixel_count: number;
  valid_coverage_fraction: number;
  resampling_applied: boolean;
  resampling_method: string | null;
  observability: TerrainScaleObservabilityReport;
  derivatives: Record<string, TerrainDerivativeMetadata>;
  observability_class_counts: Record<string, number>;
  classification: string;
}

export interface ScaleComparisonEntry {
  dataset_id: string;
  product_id: string;
  scale_category: string;
  native_resolution_m: number;
  vertical_datum: string;
  valid_pixel_count: number;
  valid_coverage_fraction: number;
  elevation_min_m: number | null;
  elevation_max_m: number | null;
  elevation_mean_m: number | null;
  slope_mean_deg: number | null;
  slope_p95_deg: number | null;
  tri_mean_m: number | null;
  smoothing_attenuation_note: string;
}

export interface MultiScaleTerrainComparisonResponse {
  study_bounds: Record<string, number>;
  compared_datasets: ScaleComparisonEntry[];
  pairwise_cross_scale_deltas: Array<Record<string, unknown>>;
  never_interprets_scale_diff_as_temporal_change: boolean;
  scientific_explanation: string;
  limitations: string[];
}

export interface ChangeGateStatus {
  gate_name: string;
  passed: boolean;
  detail: string;
}

export interface TerrainChangeEvaluationResult {
  dataset_a_id: string;
  dataset_b_id: string;
  study_bounds: Record<string, number>;
  status: string;
  evaluable: boolean;
  gates: ChangeGateStatus[];
  failure_reasons: string[];
  propagated_vertical_uncertainty_1sigma_m: number | null;
  observed_mean_delta_m: number | null;
  observed_max_abs_delta_m: number | null;
  significant_change_pixel_fraction: number | null;
  limitations: string[];
}

export interface MorphologyReviewRecord {
  candidate_id: string;
  dataset_id: string;
  action: string;
  reviewer_id: string;
  reviewed_at_utc: string;
  updated_epistemic_state: string;
  classification: string;
  origin_note: string;
  annotation_note: string | null;
  assigned_feature_class: string | null;
}

export interface MorphologicalFeatureCandidate {
  candidate_id: string;
  feature_class: string;
  epistemic_state: string;
  classification: string;
  source_dataset_ids: string[];
  source_product_ids: string[];
  supporting_evidence_modalities: string[];
  centroid_lat: number;
  centroid_lon_east: number;
  bounds: Record<string, number>;
  geometry_geojson: GeoJsonGeometry;
  measurable_geometry: Record<string, number | null>;
  min_required_resolution_m: number;
  observed_resolution_m: number;
  detection_method: string;
  descriptive_summary: string;
  geological_interpretation_warning: string;
  nodata_border_rejected: boolean;
  rejection_reason: string | null;
  review_status: string;
  human_review: MorphologyReviewRecord | null;
}

export interface ResolutionGatedFeatureClassNotice {
  feature_class: string;
  detectable: boolean;
  required_max_resolution_m: number;
  available_resolution_m: number | null;
  reason: string;
}

export interface MorphologyDetectionResponse {
  dataset_id: string;
  ortho_dataset_id: string | null;
  bounds: Record<string, number>;
  engine_version: string;
  dem_resolution_m: number | null;
  ortho_resolution_m: number | null;
  valid_dem_coverage_fraction: number;
  valid_ortho_coverage_fraction: number;
  nodata_border_guard_px: number;
  candidates: MorphologicalFeatureCandidate[];
  rejected_nodata_border_candidates: MorphologicalFeatureCandidate[];
  resolution_gating: ResolutionGatedFeatureClassNotice[];
  limitations: string[];
  persisted_review_count: number;
}

export interface RoverLocationComponents {
  rover_position: Record<string, unknown> | null;
  camera_pointing: Record<string, unknown> | null;
  target_location: Record<string, unknown> | null;
  instrument_footprint_m: number | null;
  sample_location: Record<string, unknown> | null;
  effective_reference_point: Record<string, number> | null;
}

export interface RoverOrbitalAssociationRecord {
  association_version: string;
  observation_id: string;
  mission: string;
  instrument: string;
  product_id: string;
  orbital_dataset_id: string;
  orbital_product_id: string;
  target_or_feature_id: string | null;
  association_state: string;
  location_components: RoverLocationComponents;
  rover_location_provenance: string;
  location_semantic_type: string;
  rover_localization_uncertainty_m: number | null;
  orbital_registration_uncertainty_m: number | null;
  spatial_distance_to_feature_m: number | null;
  acquisition_sol: number | null;
  acquisition_time: string | null;
  instrument_measurement_type: string;
  observation_footprint_m: number | null;
  orbital_pixel_footprint_m: number | null;
  scale_disparity_ratio: number | null;
  confirms_entire_orbital_pixel: boolean;
  scale_disparity_statement: string;
  limitations: string[];
  classification: string;
}

export interface ScalePyramidTier {
  tier_name: string;
  dataset_id: string;
  product_id: string;
  modality: string;
  native_resolution_m: number;
  min_viewport_span_m: number;
  max_viewport_span_m: number;
  recommended_grid_dim: number;
  intersects_viewport: boolean;
  has_overviews: boolean;
  overview_factors: number[];
  resampling_warning: string | null;
}

export interface SourceTransitionWarning {
  from_dataset_id: string;
  to_dataset_id: string;
  transition_span_m: number;
  resolution_jump_factor: number;
  vertical_datum_warning: string | null;
}

export interface MultiResolutionPyramidPlan {
  bounds: Record<string, number>;
  viewport_span_m: number;
  requested_viewport_px: number;
  target_pixel_size_m: number;
  selected_dem_dataset_id: string | null;
  selected_optical_dataset_id: string | null;
  selected_native_resolution_m: number | null;
  upsampling_prevented: boolean;
  available_tiers: ScalePyramidTier[];
  source_transitions: SourceTransitionWarning[];
  delivery_constraints: string[];
  cache_digest_preview: string | null;
}

export interface CacheInvalidationEvent {
  invalidated_at_utc: string;
  scope: string;
  dataset_id: string | null;
  cleared_entries: number;
  reason: string;
  operator: string;
}

export interface SpatialCacheStatus {
  engine_version: string;
  key_dimensions: string[];
  mesh_tile_cache: {
    entries: number;
    max_entries: number;
    hits: number;
    misses: number;
    [key: string]: unknown;
  };
  recent_invalidations: CacheInvalidationEvent[];
}

// ============================================================================
// Prompt 1: Multi-Astronaut Mission Foundation, Auth, SOS, Observations,
// Landing-Site Intelligence & Offline Sync Contracts
// ============================================================================

export type MissionRole = "MISSION_LEAD" | "ASTRONAUT" | "MISSION_OPERATOR";
export type CrewConnectionStatus =
  | "CONNECTED"
  | "DISCONNECTED"
  | "POSITION_STALE"
  | "POSITION_UNAVAILABLE"
  | "LOCATION_SHARING_DISABLED"
  | "UNKNOWN";

export type ObservationCategory =
  | "MINERAL_DISCOVERY"
  | "HAZARD_REPORT"
  | "SAMPLE_NOTE"
  | "TERRAIN_ANOMALY"
  | "SCIENCE_NOTE";

export type ObservationEpistemicState =
  | "USER_REPORTED"
  | "UNVERIFIED"
  | "CORROBORATED_BY_EVIDENCE"
  | "CONTESTED"
  | "RETRACTED";

export type SosStatus =
  | "ACTIVE"
  | "DELIVERED_TO_CREW_DEVICE"
  | "ACKNOWLEDGED_BY_CREW"
  | "RESOLVED"
  | "CANCELLED";

export interface OperationalAssumedField {
  value: number | null;
  unit: string;
  classification: "USER_ASSUMED" | "NOT_PROVIDED";
  updated_at_utc?: string | null;
  source?: string | null;
}

export interface AstronautProfile {
  astronaut_id: string;
  email: string;
  display_name: string;
  is_active: boolean;
  body_mass_kg: number | null;
  body_mass_meta: OperationalAssumedField;
  suit_mass_kg: number | null;
  suit_mass_meta: OperationalAssumedField;
  equipment_mass_kg: number | null;
  equipment_mass_meta: OperationalAssumedField;
  total_mass_kg: number | null;
  mobility_constraints?: string | null;
  emergency_contact?: string | null;
  profile_visibility: "mission_members" | "private";
  profile_edit_history: Array<Record<string, unknown>>;
  is_demo?: boolean;
  created_at_utc: string;
  updated_at_utc: string;
}

export interface DemoCredentialsConfig {
  enabled: boolean;
  demo_mission_id?: string | null;
  email?: string | null;
  password?: string | null;
  display_name?: string | null;
  account_label: string;
  disclaimer: string;
}

export interface AuthSessionState {
  authenticated: boolean;
  astronaut?: AstronautProfile | null;
  csrf_token?: string | null;
  session_id?: string | null;
}

export interface MissionSummary {
  mission_id: string;
  name: string;
  description: string;
  objective: string;
  lead_astronaut_id: string;
  operating_region?: string | null;
  planned_start_utc?: string | null;
  planned_end_utc?: string | null;
  visibility: string;
  membership_policy: string;
  status: string;
  landing_site_status: "LANDING_SITE_UNCONFIGURED" | "REGISTERED";
  my_role: MissionRole;
  active_member_count: number;
  active_sos_count: number;
  is_demo?: boolean;
  created_at_utc: string;
  updated_at_utc: string;
}

export interface MissionInvitation {
  invite_id: string;
  mission_id: string;
  created_by: string;
  role_on_join: MissionRole;
  single_use: boolean;
  max_uses?: number | null;
  uses_count: number;
  expires_at_utc: string;
  revoked_at_utc?: string | null;
  created_at_utc: string;
  invite_token?: string | null;
}

export interface CrewPosition {
  position_id: string;
  mission_id: string;
  astronaut_id: string;
  display_name?: string | null;
  latitude: number;
  longitude_east: number;
  crs: string;
  latitude_convention: string;
  longitude_direction: string;
  elevation_m?: number | null;
  elevation_source?: string | null;
  uncertainty_m?: number | null;
  source_id: string;
  source_classification: string;
  sequence_number: number;
  measured_at_utc: string;
  received_at_utc: string;
  age_seconds: number;
  is_stale: boolean;
  validation_status: string;
}

export interface CrewMember {
  astronaut_id: string;
  display_name: string;
  role: MissionRole;
  membership_status: "ACTIVE" | "LEFT" | "REMOVED";
  location_sharing_enabled: boolean;
  connection_status: CrewConnectionStatus;
  joined_at_utc: string;
  latest_position?: CrewPosition | null;
  body_mass_kg?: number | null;
  suit_mass_kg?: number | null;
  equipment_mass_kg?: number | null;
  total_mass_kg?: number | null;
  mass_classification?: string | null;
  emergency_contact?: string | null;
  is_demo?: boolean;
}

export interface VoiceNoteRecord {
  voice_note_id: string;
  mission_id: string;
  astronaut_id: string;
  display_name?: string | null;
  linked_event_type?: string | null;
  linked_event_id?: string | null;
  mime_type: string;
  file_size_bytes: number;
  duration_seconds?: number | null;
  sha256_checksum: string;
  upload_status: string;
  playback_url: string;
  created_at_utc: string;
}

export interface SosAcknowledgement {
  ack_id: string;
  sos_id: string;
  astronaut_id: string;
  display_name: string;
  ack_type: "DELIVERED_TO_CREW_DEVICE" | "ACKNOWLEDGED_BY_CREW" | "RESOLVED" | "CANCELLED";
  note?: string | null;
  created_at_utc: string;
}

export interface SosEvent {
  sos_id: string;
  mission_id: string;
  astronaut_id: string;
  astronaut_display_name: string;
  event_type: string;
  status: SosStatus;
  client_event_id?: string | null;
  latitude?: number | null;
  longitude_east?: number | null;
  elevation_m?: number | null;
  crs?: string | null;
  position_source?: string | null;
  position_classification?: string | null;
  position_age_s?: number | null;
  position_status: string;
  message?: string | null;
  voice_note?: VoiceNoteRecord | null;
  acknowledgements: SosAcknowledgement[];
  created_at_utc: string;
  server_received_at_utc: string;
  updated_at_utc: string;
}

export interface FieldObservation {
  observation_id: string;
  mission_id: string;
  astronaut_id: string;
  astronaut_display_name: string;
  client_event_id?: string | null;
  version: number;
  latitude?: number | null;
  longitude_east?: number | null;
  elevation_m?: number | null;
  crs: string;
  coordinate_source: string;
  uncertainty_m?: number | null;
  target_id?: string | null;
  category: ObservationCategory;
  species_canonical_id?: string | null;
  species_display_name?: string | null;
  description: string;
  epistemic_state: ObservationEpistemicState;
  instrument_id?: string | null;
  source_product_id?: string | null;
  calibration_metadata?: string | null;
  evidence_ids: string[];
  voice_note?: VoiceNoteRecord | null;
  offline_created_at_utc?: string | null;
  synced_at_utc?: string | null;
  reviewed_by?: string | null;
  review_note?: string | null;
  annotations: Array<Record<string, unknown>>;
  audit_history: Array<Record<string, unknown>>;
  created_at_utc: string;
  updated_at_utc: string;
}

export interface GazetteerSiteRecord {
  record_id: string;
  name: string;
  region?: string | null;
  latitude: number;
  longitude_east: number;
  crs: string;
  source: string;
  dataset_id: string;
  coverage_verified: boolean;
  elevation_m?: number | null;
  uncertainty_m?: number | null;
}

export interface LandingSiteRecord {
  landing_site_id: string;
  mission_id: string;
  name: string;
  latitude: number;
  longitude_east: number;
  crs: string;
  latitude_convention: string;
  longitude_direction: string;
  source: string;
  source_record_id?: string | null;
  uncertainty_m?: number | null;
  elevation_m?: number | null;
  terrain_dataset_id?: string | null;
  dem_coverage_state: "COVERED_DEM" | "OUTSIDE_EVALUATED_DEM_COVERAGE" | "UNVERIFIED_EXTERNAL";
  registration_state: "LANDING_SITE_UNCONFIGURED" | "REGISTERED";
  updated_by: string;
  history: Array<Record<string, unknown>>;
  created_at_utc: string;
  updated_at_utc: string;
}

export interface LandingSitePerimeter {
  perimeter_id: string;
  mission_id: string;
  landing_site_id: string;
  status:
    | "EVALUATED_WITH_VALIDATED_DEM"
    | "INDETERMINATE_OUTSIDE_DEM"
    | "INDETERMINATE_MISSING_CONSTRAINTS";
  classification_label: string;
  algorithm_id: string;
  algorithm_version: string;
  terrain_dataset_id?: string | null;
  native_resolution_m?: number | null;
  coverage_fraction?: number | null;
  geometry_geojson?: Record<string, unknown> | null;
  excluded_regions_geojson?: Record<string, unknown> | null;
  constraints_used: Record<string, unknown>;
  constraints_missing: string[];
  limitations: string[];
  provenance: Record<string, unknown>;
  operator_approved: boolean;
  approved_by?: string | null;
  approved_at_utc?: string | null;
  created_at_utc: string;
}

export interface LandingSiteBundle {
  mission_id: string;
  landing_site_status: "LANDING_SITE_UNCONFIGURED" | "REGISTERED";
  landing_site?: LandingSiteRecord | null;
  perimeter?: LandingSitePerimeter | null;
}

export interface MissionEventRecord {
  event_id: string;
  mission_id: string;
  actor_id: string;
  event_type: string;
  client_timestamp_utc?: string | null;
  server_timestamp_utc: string;
  payload_schema_version: string;
  event_seq: number;
  correlation_id: string;
  client_event_id?: string | null;
  provenance: Record<string, unknown>;
  auth_context: Record<string, unknown>;
  payload: Record<string, unknown>;
}

export type NavigationState =
  | "NOT_CONFIGURED"
  | "READY_FOR_OPERATOR_REVIEW"
  | "AWAITING_OPERATOR_APPROVAL"
  | "ACTIVE"
  | "POSITION_UNAVAILABLE"
  | "POSITION_STALE"
  | "ROUTE_DEVIATION_DETECTED"
  | "OBSTRUCTION_REPORTED"
  | "REPLANNING_REQUIRED"
  | "RETURN_REQUESTED"
  | "RETURN_ROUTE_ACTIVE"
  | "PAUSED"
  | "COMPLETED"
  | "ABORTED"
  | "EMERGENCY";

export interface NavigationSegmentDetail {
  segment_id: string;
  segment_index: number;
  start_lat: number;
  start_lon: number;
  end_lat: number;
  end_lon: number;
  crs: string;
  surface_distance_m: number;
  start_elevation_m?: number | null;
  end_elevation_m?: number | null;
  elevation_gain_m?: number | null;
  elevation_loss_m?: number | null;
  slope_deg?: number | null;
  roughness_m?: number | null;
  source_dem: string;
  effective_resolution_m?: number | null;
  valid_pixel_coverage_pct?: number | null;
  terrain_uncertainty_m?: number | null;
  registration_uncertainty_m?: number | null;
  traversability_evidence_state: string;
  candidate_obstacles: string[];
  known_data_gaps: string[];
  limitation_note: string;
}

export interface NavigationInstructionDetail {
  step_index: number;
  segment_id: string;
  instruction_text: string;
  true_north_bearing_deg: number;
  grid_north_bearing_deg?: number | null;
  bearing_reference: string;
  heading_status: "USER_ENTERED" | "DEVICE_REPORTED" | "UNAVAILABLE";
  distance_m: number;
  remaining_distance_m: number;
  elevation_change_m?: number | null;
  slope_deg?: number | null;
  support_state: "SUPPORTED" | "LIMITED" | "UNKNOWN";
  terrain_limitation?: string | null;
  is_arrival: boolean;
}

export interface NavigationProgressDetail {
  progress_status: "AVAILABLE" | "PROGRESS UNAVAILABLE";
  localization_banner: string;
  localization_freshness: string;
  localization_epistemic_classification: string;
  position_timestamp_utc?: string | null;
  position_source?: string | null;
  accuracy_m?: number | null;
  nearest_segment_index?: number | null;
  distance_to_next_waypoint_m?: number | null;
  remaining_route_distance_m?: number | null;
  completed_fraction?: number | null;
  cross_track_deviation_m?: number | null;
  deviation_state:
    | "NOT_CONFIGURED"
    | "WITHIN_THRESHOLD"
    | "DEVIATION_DETECTED"
    | "UNAVAILABLE_ACCURACY_OR_POSITION";
  deviation_limitation?: string | null;
}

export interface TurnbackAssessmentRecord {
  state:
    | "WITHIN_CONFIGURED_PLANNING_CONSTRAINTS"
    | "TURNBACK_REVIEW_REQUIRED"
    | "RETURN_ROUTE_UNAVAILABLE"
    | "RESOURCE_BUDGET_INCOMPLETE"
    | "INSUFFICIENT_LOCALIZATION"
    | "INSUFFICIENT_TERRAIN_EVIDENCE"
    | "INDETERMINATE";
  evaluated_at_utc: string;
  outbound_distance_m?: number | null;
  return_distance_m?: number | null;
  return_estimated_duration_s?: number | null;
  configured_max_duration_s?: number | null;
  return_route_available: boolean;
  return_route_status: string;
  resource_budget_status: string;
  missing_inputs: string[];
  decision_support_note: string;
  return_route_vertices: Array<Record<string, unknown>>;
  provenance: Record<string, unknown>;
}

export interface ObstructionReportRecord {
  obstruction_id: string;
  nav_session_id: string;
  mission_id: string;
  reported_by: string;
  segment_index?: number | null;
  latitude: number;
  longitude: number;
  location_source: string;
  description: string;
  voice_note_id?: string | null;
  attachment_note?: string | null;
  review_state: string;
  epistemic_classification: string;
  created_at_utc: string;
}

export interface NavigationSessionRecord {
  nav_session_id: string;
  mission_id: string;
  astronaut_id: string;
  state: NavigationState;
  allowed_transitions: NavigationState[];
  navigation_mode: "OPERATOR_SUPERVISED_EVA" | "MANUAL_WAYPOINT_CHECK" | "RETURN_TO_BASE";
  route_id?: string | null;
  route_dataset_id: string;
  route_crs: string;
  return_destination_name: string;
  return_destination_lat: number;
  return_destination_lon: number;
  deviation_threshold_m?: number | null;
  active_segment_index: number;
  segments: NavigationSegmentDetail[];
  instructions: NavigationInstructionDetail[];
  progress: NavigationProgressDetail;
  turnback?: TurnbackAssessmentRecord | null;
  obstructions: ObstructionReportRecord[];
  candidate_replan?: Record<string, unknown> | null;
  route_limitations: string[];
  approved_by?: string | null;
  approved_at_utc?: string | null;
  last_state_reason?: string | null;
  created_at_utc: string;
  updated_at_utc: string;
}


