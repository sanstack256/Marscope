const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
export const API_BASE_URL =
  configuredApiBase && configuredApiBase.startsWith("/")
    ? configuredApiBase.replace(/\/+$/, "") || "/api"
    : process.env.NODE_ENV === "production" && configuredApiBase
      ? configuredApiBase.replace(/\/+$/, "")
      : "/api";

export const MARS_CONSTANTS = {
  SURFACE_GRAVITY_M_S2: 3.72076,
  DATUM: "IAU2000:49900 (Mars Mean Equator / IAU Sphere)",
  DEFAULT_CRS: "IAU2000:49900",
} as const;

export interface NavItemDef {
  href: string;
  label: string;
  icon: string;
  badge?: string;
}

export interface NavGroupDef {
  id: string;
  label: string;
  items: NavItemDef[];
}

export const NAVIGATION_GROUPS: NavGroupDef[] = [
  {
    id: "command",
    label: "Command",
    items: [
      { href: "/", label: "Mission Control", icon: "Compass" },
      { href: "/missions", label: "Missions & Access", icon: "ShieldCheck" },
      { href: "/crew", label: "Crew Roster", icon: "Users" },
      { href: "/emergency", label: "Emergency SOS", icon: "AlertOctagon" },
    ],
  },
  {
    id: "field_ops",
    label: "Field Ops",
    items: [
      { href: "/active-navigation", label: "Active Navigation", icon: "Navigation", badge: "P2" },
      { href: "/landing-site", label: "Landing Site & 3D Bounds", icon: "Flag" },
      { href: "/observations", label: "Field Observations", icon: "Microscope" },
      { href: "/eva-operations", label: "EVA Operations", icon: "Activity" },
    ],
  },
  {
    id: "terrain_map",
    label: "Terrain & Map",
    items: [
      { href: "/explorer", label: "Surface Explorer 3D", icon: "Globe2" },
      { href: "/spatial-intelligence", label: "Spatial Intelligence", icon: "Radar" },
      { href: "/terrain", label: "Terrain Analysis", icon: "Mountain" },
      { href: "/imagery", label: "Orbital Imagery", icon: "Satellite" },
    ],
  },
  {
    id: "planning_routes",
    label: "Planning & Routes",
    items: [
      { href: "/planner", label: "Route Planner", icon: "Route" },
      { href: "/routes", label: "Saved Traverses", icon: "Waypoints" },
      { href: "/simulation", label: "EVA Simulation", icon: "Gauge" },
      { href: "/mission-readiness", label: "Mission Readiness", icon: "CheckCircle2" },
    ],
  },
  {
    id: "science_evidence",
    label: "Science & Evidence",
    items: [
      { href: "/targets", label: "Science Targets", icon: "Target" },
      { href: "/science-campaign", label: "Science Campaign", icon: "FlaskConical" },
      { href: "/evidence", label: "Evidence Intelligence", icon: "FileSearch" },
    ],
  },
  {
    id: "system",
    label: "System",
    items: [
      { href: "/profile", label: "Astronaut Profile", icon: "UserCog" },
      { href: "/settings", label: "System Settings", icon: "Settings" },
    ],
  },
];

export const NAVIGATION_PAGES = NAVIGATION_GROUPS.flatMap((g) => g.items);

export function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${escaped}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Cookie + Double-Submit CSRF Fetch Wrapper.
 * Sends HttpOnly session cookies automatically and injects X-CSRF-Token on mutating HTTP methods.
 */
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const url = input.startsWith("http") || input.startsWith("/api") ? input : `${API_BASE_URL}${input}`;
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers || {});

  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = readCookie("marscope_csrf");
    if (csrf && !headers.has("X-CSRF-Token")) {
      headers.set("X-CSRF-Token", csrf);
    }
    if (init.body && typeof init.body === "string" && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
  }

  return fetch(url, {
    ...init,
    headers,
    credentials: "include",
    cache: init.cache ?? "no-store",
  });
}
