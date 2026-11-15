/**
 * MARSCOPE UI Configuration Constants
 * Contains only static UI metadata and navigation structure — zero operational planetary measurements.
 */

export const APP_NAME = "MARSCOPE";
export const APP_SUBTITLE = "Martian Surface Intelligence & Exploration System";

// Use Next.js rewrite proxy (/api -> http://127.0.0.1:8000/api) to prevent CORS issues
export const API_BASE_URL = "/api";

export const NAVIGATION_PAGES = [
  {
    name: "Mission Overview",
    href: "/",
    icon: "LayoutDashboard",
    description: "Backend status, dataset readiness & exploration workspace links",
  },
  {
    name: "Surface Explorer",
    href: "/explorer",
    icon: "Globe2",
    badge: "3D",
    description: "Interactive Mars orbital imagery, terrain overlays & coordinate inspection",
  },
  {
    name: "Terrain Intelligence",
    href: "/terrain",
    icon: "Mountain",
    description: "Validated DEM statistics, slope gradients & roughness (TRI)",
  },
  {
    name: "Target Explorer",
    href: "/targets",
    icon: "Telescope",
    description: "Verified geological targets and parsed in-situ observations",
  },
  {
    name: "Route Planner",
    href: "/planner",
    icon: "Compass",
    badge: "3D A*",
    description: "3D DEM surface route optimization & turn-by-turn astronaut navigation",
  },
  {
    name: "Route Comparison",
    href: "/routes",
    icon: "GitCompare",
    description: "Conservative, Balanced & Science-Priority multi-route trade-off comparison",
  },
  {
    name: "Mission Simulation",
    href: "/simulation",
    icon: "PlayCircle",
    description: "Synchronized 3D EVA playback, leg grades & gravitational work profile",
  },
  {
    name: "Evidence & Provenance",
    href: "/evidence",
    icon: "Database",
    description: "NASA source verification, dataset acquisition & DEM processing",
  },
  {
    name: "Mission Assumptions",
    href: "/settings",
    icon: "Settings",
    description: "Traceable physics parameters & backend diagnostics",
  },
];
