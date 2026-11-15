"use client";

import { create } from "zustand";
import { apiFetch, API_BASE_URL } from "../lib/constants";
import {
  enqueueOfflineEvent,
  flushOfflineQueue,
  listOfflineEvents,
  OfflineQueuedEvent,
} from "../lib/offlineQueue";
import {
  AstronautProfile,
  AuthSessionState,
  CrewMember,
  CrewPosition,
  FieldObservation,
  LandingSiteBundle,
  MissionEventRecord,
  MissionInvitation,
  MissionSummary,
  SosEvent,
} from "../types";

export type StreamConnectionState = "CONNECTED" | "RECONNECTING" | "DISCONNECTED" | "OFFLINE";

interface AuthMissionState {
  authChecked: boolean;
  authenticated: boolean;
  astronaut: AstronautProfile | null;
  authError: string | null;

  missions: MissionSummary[];
  activeMissionId: string | null;
  activeMission: MissionSummary | null;
  crew: CrewMember[];
  positions: CrewPosition[];
  invitations: MissionInvitation[];
  sosEvents: SosEvent[];
  observations: FieldObservation[];
  landingSiteBundle: LandingSiteBundle | null;
  missionEvents: MissionEventRecord[];

  offlineQueue: OfflineQueuedEvent[];
  browserOnline: boolean;
  streamState: StreamConnectionState;
  sosDrawerOpen: boolean;
  isLoadingMissionData: boolean;

  checkSession: () => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<boolean>;
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  updateProfile: (patch: Record<string, unknown>) => Promise<AstronautProfile | null>;

  loadMissions: () => Promise<void>;
  resetDemoMission: () => Promise<boolean>;
  selectMission: (missionId: string | null) => Promise<void>;
  createMission: (payload: {
    name: string;
    description?: string;
    objective?: string;
    operating_region?: string;
  }) => Promise<MissionSummary | null>;
  joinMission: (inviteToken: string) => Promise<MissionSummary | null>;

  refreshMissionWorkspace: (missionId?: string) => Promise<void>;
  ingestPosition: (payload: {
    latitude: number;
    longitude: number;
    crs?: string;
    source_id: string;
    source_classification: "TELEMETRY_PROVIDER" | "LOCALIZATION_SOLVER" | "USER_PROVIDED";
    uncertainty_m?: number;
    sequence_number?: number;
  }) => Promise<{ ok: boolean; queuedOffline?: boolean; error?: string }>;

  triggerSos: (payload: {
    message?: string;
    voice_note_id?: string | null;
    explicit_latitude?: number | null;
    explicit_longitude?: number | null;
  }) => Promise<{ ok: boolean; sos?: SosEvent; queuedOffline?: boolean; error?: string }>;
  acknowledgeSos: (sosId: string, note?: string) => Promise<void>;
  resolveSos: (sosId: string, note?: string) => Promise<void>;
  cancelSos: (sosId: string, note?: string) => Promise<void>;
  setSosDrawerOpen: (open: boolean) => void;

  createFieldObservation: (payload: Record<string, unknown>) => Promise<{
    ok: boolean;
    observation?: FieldObservation;
    queuedOffline?: boolean;
    error?: string;
  }>;

  syncOfflineEventsNow: () => Promise<void>;
  connectMissionStream: (missionId: string) => () => void;
  setBrowserOnline: (online: boolean) => void;
}

const ACTIVE_MISSION_STORAGE_KEY = "marscope.active_mission_id";

function getPersistedMissionId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(ACTIVE_MISSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function setPersistedMissionId(missionId: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (missionId) {
      window.localStorage.setItem(ACTIVE_MISSION_STORAGE_KEY, missionId);
    } else {
      window.localStorage.removeItem(ACTIVE_MISSION_STORAGE_KEY);
    }
  } catch {
    // ignore storage quota errors
  }
}

export const useAuthMissionStore = create<AuthMissionState>((set, get) => ({
  authChecked: false,
  authenticated: false,
  astronaut: null,
  authError: null,

  missions: [],
  activeMissionId: null,
  activeMission: null,
  crew: [],
  positions: [],
  invitations: [],
  sosEvents: [],
  observations: [],
  landingSiteBundle: null,
  missionEvents: [],

  offlineQueue: [],
  browserOnline: true,
  streamState: "DISCONNECTED",
  sosDrawerOpen: false,
  isLoadingMissionData: false,

  setSosDrawerOpen: (open) => set({ sosDrawerOpen: open }),
  setBrowserOnline: (online) => {
    set({ browserOnline: online });
    if (online) {
      void get().syncOfflineEventsNow();
    } else {
      set({ streamState: "OFFLINE" });
    }
  },

  checkSession: async () => {
    try {
      const res = await apiFetch("/auth/session");
      if (!res.ok) {
        set({ authChecked: true, authenticated: false, astronaut: null });
        return;
      }
      const data: AuthSessionState = await res.json();
      set({
        authChecked: true,
        authenticated: Boolean(data.authenticated),
        astronaut: data.astronaut ?? null,
        authError: null,
      });
      if (data.authenticated) {
        await get().loadMissions();
      }
    } catch {
      set({ authChecked: true, authenticated: false, astronaut: null });
    }
  },

  register: async (email, password, displayName) => {
    set({ authError: null });
    try {
      const res = await apiFetch("/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password, display_name: displayName }),
      });
      const body = await res.json();
      if (!res.ok) {
        set({ authError: body.detail || "Registration failed." });
        return false;
      }
      await get().loadMissions();
      set({
        authChecked: true,
        authenticated: true,
        astronaut: body.astronaut,
        authError: null,
      });
      return true;
    } catch (err) {
      set({ authError: err instanceof Error ? err.message : "Network error" });
      return false;
    }
  },

  login: async (email, password) => {
    set({ authError: null });
    try {
      const res = await apiFetch("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      const body = await res.json();
      if (!res.ok) {
        set({ authError: body.detail || "Invalid credentials." });
        return false;
      }
      await get().loadMissions();
      set({
        authChecked: true,
        authenticated: true,
        astronaut: body.astronaut,
        authError: null,
      });
      return true;
    } catch (err) {
      set({ authError: err instanceof Error ? err.message : "Network error" });
      return false;
    }
  },

  logout: async () => {
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      // ignore network failure on logout
    }
    setPersistedMissionId(null);
    if (typeof window !== "undefined") {
      try {
        window.localStorage.removeItem("marscope_demo_tour_state");
      } catch {
        // ignore
      }
    }
    set({
      authenticated: false,
      astronaut: null,
      missions: [],
      activeMissionId: null,
      activeMission: null,
      crew: [],
      positions: [],
      invitations: [],
      sosEvents: [],
      observations: [],
      landingSiteBundle: null,
      missionEvents: [],
      streamState: "DISCONNECTED",
    });
  },

  resetDemoMission: async () => {
    const res = await apiFetch("/demo/reset", { method: "POST" });
    if (!res.ok) return false;
    await get().loadMissions();
    const mId = get().activeMissionId;
    if (mId) {
      await get().refreshMissionWorkspace(mId);
    }
    return true;
  },

  updateProfile: async (patch) => {
    const res = await apiFetch("/auth/profile", {
      method: "PUT",
      body: JSON.stringify(patch),
    });
    if (!res.ok) return null;
    const updated: AstronautProfile = await res.json();
    set({ astronaut: updated });
    return updated;
  },

  loadMissions: async () => {
    const res = await apiFetch("/missions");
    if (!res.ok) return;
    const missions: MissionSummary[] = await res.json();
    const persisted = getPersistedMissionId();
    const currentId = get().activeMissionId;
    const chosen =
      missions.find((m) => m.mission_id === currentId) ||
      missions.find((m) => m.mission_id === persisted) ||
      missions[0] ||
      null;

    set({
      missions,
      activeMissionId: chosen?.mission_id ?? null,
      activeMission: chosen,
    });
    if (chosen) {
      setPersistedMissionId(chosen.mission_id);
      await get().refreshMissionWorkspace(chosen.mission_id);
    }
  },

  selectMission: async (missionId) => {
    if (!missionId) {
      setPersistedMissionId(null);
      set({
        activeMissionId: null,
        activeMission: null,
        crew: [],
        positions: [],
        invitations: [],
        sosEvents: [],
        observations: [],
        landingSiteBundle: null,
        missionEvents: [],
      });
      return;
    }
    const found = get().missions.find((m) => m.mission_id === missionId) ?? null;
    setPersistedMissionId(missionId);
    set({ activeMissionId: missionId, activeMission: found });
    await get().refreshMissionWorkspace(missionId);
  },

  createMission: async (payload) => {
    const res = await apiFetch("/missions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (!res.ok) return null;
    const created: MissionSummary = await res.json();
    await get().loadMissions();
    await get().selectMission(created.mission_id);
    return created;
  },

  joinMission: async (inviteToken) => {
    const res = await apiFetch("/missions/join", {
      method: "POST",
      body: JSON.stringify({ invite_token: inviteToken }),
    });
    if (!res.ok) return null;
    const joined: MissionSummary = await res.json();
    await get().loadMissions();
    await get().selectMission(joined.mission_id);
    return joined;
  },

  refreshMissionWorkspace: async (explicitMissionId) => {
    const missionId = explicitMissionId || get().activeMissionId;
    if (!missionId) return;
    set({ isLoadingMissionData: true });
    try {
      const [missionR, crewR, posR, sosR, obsR, lsR, evR] = await Promise.all([
        apiFetch(`/missions/${missionId}`),
        apiFetch(`/missions/${missionId}/crew`),
        apiFetch(`/missions/${missionId}/positions`),
        apiFetch(`/missions/${missionId}/sos`),
        apiFetch(`/missions/${missionId}/observations`),
        apiFetch(`/missions/${missionId}/landing-site`),
        apiFetch(`/missions/${missionId}/events?limit=60`),
      ]);
      const activeMission = missionR.ok ? ((await missionR.json()) as MissionSummary) : get().activeMission;
      const crew = crewR.ok ? ((await crewR.json()) as CrewMember[]) : [];
      const positions = posR.ok ? ((await posR.json()) as CrewPosition[]) : [];
      const sosEvents = sosR.ok ? ((await sosR.json()) as SosEvent[]) : [];
      const observations = obsR.ok ? ((await obsR.json()) as FieldObservation[]) : [];
      const landingSiteBundle = lsR.ok ? ((await lsR.json()) as LandingSiteBundle) : null;
      const missionEvents = evR.ok ? ((await evR.json()) as MissionEventRecord[]) : [];
      const queued = await listOfflineEvents(missionId);

      const hasUnackSos = sosEvents.some(
        (s) => s.status === "ACTIVE" || s.status === "DELIVERED_TO_CREW_DEVICE"
      );

      set({
        activeMission,
        crew,
        positions,
        sosEvents,
        observations,
        landingSiteBundle,
        missionEvents,
        offlineQueue: queued,
        sosDrawerOpen: hasUnackSos ? true : get().sosDrawerOpen,
      });

      if (activeMission && ["MISSION_LEAD", "MISSION_OPERATOR"].includes(activeMission.my_role)) {
        const invR = await apiFetch(`/missions/${missionId}/invitations`);
        if (invR.ok) {
          set({ invitations: await invR.json() });
        }
      }
    } finally {
      set({ isLoadingMissionData: false });
    }
  },

  ingestPosition: async (payload) => {
    const missionId = get().activeMissionId;
    if (!missionId) return { ok: false, error: "No active mission selected." };
    const clientEventId = crypto.randomUUID();
    const body = { ...payload, crs: payload.crs || "IAU2000:49900", client_event_id: clientEventId };
    try {
      const res = await apiFetch(`/missions/${missionId}/positions`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Position ingest failed." }));
        return { ok: false, error: err.detail || "Position ingest failed." };
      }
      await get().refreshMissionWorkspace(missionId);
      return { ok: true };
    } catch {
      await enqueueOfflineEvent({
        client_event_id: clientEventId,
        mission_id: missionId,
        event_kind: "CREW_POSITION",
        endpoint: `/missions/${missionId}/positions`,
        method: "POST",
        payload: body,
        created_at_utc: new Date().toISOString(),
        status: "QUEUED_OFFLINE",
        attempts: 0,
      });
      set({ offlineQueue: await listOfflineEvents(missionId) });
      return { ok: true, queuedOffline: true };
    }
  },

  triggerSos: async (payload) => {
    const missionId = get().activeMissionId;
    if (!missionId) return { ok: false, error: "No active mission selected." };
    const clientEventId = crypto.randomUUID();
    const clientTs = new Date().toISOString();
    const body = {
      ...payload,
      client_event_id: clientEventId,
      client_timestamp_utc: clientTs,
    };
    try {
      const res = await apiFetch(`/missions/${missionId}/sos`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "SOS dispatch failed." }));
        return { ok: false, error: err.detail || "SOS dispatch failed." };
      }
      const sos: SosEvent = await res.json();
      set({ sosDrawerOpen: true });
      await get().refreshMissionWorkspace(missionId);
      return { ok: true, sos };
    } catch {
      await enqueueOfflineEvent({
        client_event_id: clientEventId,
        mission_id: missionId,
        event_kind: "SOS_TRIGGER",
        endpoint: `/missions/${missionId}/sos`,
        method: "POST",
        payload: body,
        created_at_utc: clientTs,
        status: "QUEUED_OFFLINE",
        attempts: 0,
      });
      set({ offlineQueue: await listOfflineEvents(missionId) });
      return { ok: true, queuedOffline: true };
    }
  },

  acknowledgeSos: async (sosId, note) => {
    const missionId = get().activeMissionId;
    if (!missionId) return;
    await apiFetch(`/missions/${missionId}/sos/${sosId}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({ note: note || null }),
    });
    await get().refreshMissionWorkspace(missionId);
  },

  resolveSos: async (sosId, note) => {
    const missionId = get().activeMissionId;
    if (!missionId) return;
    await apiFetch(`/missions/${missionId}/sos/${sosId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ note: note || null }),
    });
    await get().refreshMissionWorkspace(missionId);
  },

  cancelSos: async (sosId, note) => {
    const missionId = get().activeMissionId;
    if (!missionId) return;
    await apiFetch(`/missions/${missionId}/sos/${sosId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ note: note || "Cancelled with audit retention" }),
    });
    await get().refreshMissionWorkspace(missionId);
  },

  createFieldObservation: async (payload) => {
    const missionId = get().activeMissionId;
    if (!missionId) return { ok: false, error: "No active mission selected." };
    const clientEventId = crypto.randomUUID();
    const nowIso = new Date().toISOString();
    const body = { ...payload, client_event_id: clientEventId };
    try {
      const res = await apiFetch(`/missions/${missionId}/observations`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Observation failed validation." }));
        return { ok: false, error: err.detail || "Observation failed validation." };
      }
      const obs: FieldObservation = await res.json();
      await get().refreshMissionWorkspace(missionId);
      return { ok: true, observation: obs };
    } catch {
      await enqueueOfflineEvent({
        client_event_id: clientEventId,
        mission_id: missionId,
        event_kind: "FIELD_OBSERVATION",
        endpoint: `/missions/${missionId}/observations`,
        method: "POST",
        payload: { ...body, offline_created_at_utc: nowIso },
        created_at_utc: nowIso,
        status: "QUEUED_OFFLINE",
        attempts: 0,
      });
      set({ offlineQueue: await listOfflineEvents(missionId) });
      return { ok: true, queuedOffline: true };
    }
  },

  syncOfflineEventsNow: async () => {
    const missionId = get().activeMissionId;
    if (!missionId) return;
    const result = await flushOfflineQueue(missionId, async (item) => {
      const res = await apiFetch(item.endpoint, {
        method: item.method,
        body: JSON.stringify(item.payload),
      });
      if (res.ok) return { ok: true, status: res.status };
      const body = await res.json().catch(() => ({}));
      return { ok: false, status: res.status, detail: body.detail };
    });
    set({ offlineQueue: await listOfflineEvents(missionId) });
    if (result.delivered > 0) {
      await get().refreshMissionWorkspace(missionId);
    }
  },

  connectMissionStream: (missionId) => {
    if (typeof EventSource === "undefined" || !missionId) return () => {};
    let closed = false;
    let source: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;

    const openStream = () => {
      if (closed) return;
      source = new EventSource(`${API_BASE_URL}/missions/${missionId}/stream`, { withCredentials: true });
      source.addEventListener("connected", () => {
        attempt = 0;
        set({ streamState: "CONNECTED" });
      });
      source.addEventListener("heartbeat", () => {
        set({ streamState: "CONNECTED" });
      });

      const refreshHandler = () => {
        void get().refreshMissionWorkspace(missionId);
      };
      for (const evType of [
        "CREW_POSITION_UPDATED",
        "CREW_LOCATION_SHARING_CHANGED",
        "CREW_MEMBER_JOINED",
        "CREW_MEMBER_LEFT",
        "CREW_MEMBER_REMOVED",
        "CREW_ROLE_UPDATED",
        "SOS_ACTIVATED",
        "SOS_DELIVERED_TO_CREW_DEVICE",
        "SOS_ACKNOWLEDGED_BY_CREW",
        "SOS_RESOLVED",
        "SOS_CANCELLED",
        "FIELD_OBSERVATION_CREATED",
        "FIELD_OBSERVATION_UPDATED",
        "FIELD_OBSERVATION_REVIEWED",
        "LANDING_SITE_REGISTERED",
        "LANDING_SITE_PERIMETER_COMPUTED",
        "LANDING_SITE_PERIMETER_APPROVED",
        "VOICE_NOTE_UPLOADED",
      ]) {
        source.addEventListener(evType, refreshHandler);
      }

      source.addEventListener("SOS_ACTIVATED", (evt: MessageEvent) => {
        set({ sosDrawerOpen: true });
        try {
          const parsed = JSON.parse(evt.data);
          const sosId = parsed?.payload?.sos_id;
          if (sosId) {
            void apiFetch(`/missions/${missionId}/sos/${sosId}/delivered`, {
              method: "POST",
              body: JSON.stringify({ note: "SSE stream delivery confirmed by client." }),
            });
          }
        } catch {
          // ignore malformed payload
        }
      });

      source.onerror = () => {
        source?.close();
        if (closed) return;
        const delayMs = Math.min(30000, 1000 * 2 ** Math.min(attempt, 5));
        attempt += 1;
        set({ streamState: navigator.onLine ? "RECONNECTING" : "OFFLINE" });
        retryTimer = setTimeout(openStream, delayMs);
      };
    };

    openStream();
    return () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      source?.close();
      set({ streamState: "DISCONNECTED" });
    };
  },
}));
