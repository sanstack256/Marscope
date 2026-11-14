/**
 * MARSCOPE Domain Type Definitions
 */

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

export interface StudyAreaInfo {
  name: string;
  center: {
    latitude: number;
    longitude: number;
  };
  bounds: {
    min_latitude: number;
    max_latitude: number;
    min_longitude: number;
    max_longitude: number;
  };
  crs: string;
  elevation_datum: string;
}

export type PlanningMode = "conservative" | "balanced" | "science_priority";

export interface ScienceTarget {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  elevation_m: number;
  geology_type: string;
  scientific_value: number;
  instrument_source: string;
  provenance_product_id: string;
}

export interface NavItem {
  name: string;
  href: string;
  icon: string;
  badge?: string;
  description: string;
}
