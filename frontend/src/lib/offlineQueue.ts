/**
 * IndexedDB Offline Event Queue Foundation (Prompt 1 Part H).
 * Queues crew observations, SOS dispatches, and location updates when offline,
 * exposes truthful delivery states (QUEUED_OFFLINE -> PENDING_DELIVERY -> DELIVERED_TO_SERVER),
 * persists across browser restarts, and replays deterministically with idempotency keys.
 */

export type OfflineQueueStatus =
  | "QUEUED_OFFLINE"
  | "PENDING_DELIVERY"
  | "DELIVERED_TO_SERVER"
  | "FAILED_RETRYABLE";

export interface OfflineQueuedEvent {
  client_event_id: string;
  mission_id: string;
  event_kind: "FIELD_OBSERVATION" | "SOS_TRIGGER" | "CREW_POSITION";
  endpoint: string;
  method: "POST" | "PUT" | "PATCH";
  payload: Record<string, unknown>;
  created_at_utc: string;
  status: OfflineQueueStatus;
  attempts: number;
  last_error?: string | null;
}

const DB_NAME = "marscope_offline_v1";
const STORE_NAME = "queued_events";
const DB_VERSION = 1;

// In-memory fallback strictly for SSR or Node unit-test environments without IndexedDB
const _memoryFallback = new Map<string, OfflineQueuedEvent>();

function hasIndexedDb(): boolean {
  return typeof indexedDB !== "undefined";
}

function openQueueDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: "client_event_id" });
        store.createIndex("by_mission", "mission_id", { unique: false });
        store.createIndex("by_status", "status", { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function enqueueOfflineEvent(item: OfflineQueuedEvent): Promise<OfflineQueuedEvent> {
  if (!hasIndexedDb()) {
    _memoryFallback.set(item.client_event_id, item);
    return item;
  }
  const db = await openQueueDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).put(item);
    tx.oncomplete = () => {
      db.close();
      resolve(item);
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

export async function listOfflineEvents(missionId?: string): Promise<OfflineQueuedEvent[]> {
  if (!hasIndexedDb()) {
    const items = Array.from(_memoryFallback.values());
    return (missionId ? items.filter((i) => i.mission_id === missionId) : items).sort((a, b) =>
      a.created_at_utc.localeCompare(b.created_at_utc)
    );
  }
  const db = await openQueueDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const store = tx.objectStore(STORE_NAME);
    const req = store.getAll();
    req.onsuccess = () => {
      db.close();
      const all = (req.result as OfflineQueuedEvent[]) || [];
      const filtered = missionId ? all.filter((i) => i.mission_id === missionId) : all;
      filtered.sort((a, b) => a.created_at_utc.localeCompare(b.created_at_utc));
      resolve(filtered);
    };
    req.onerror = () => {
      db.close();
      reject(req.error);
    };
  });
}

export async function updateOfflineEventStatus(
  clientEventId: string,
  patch: Partial<OfflineQueuedEvent>
): Promise<void> {
  if (!hasIndexedDb()) {
    const cur = _memoryFallback.get(clientEventId);
    if (cur) _memoryFallback.set(clientEventId, { ...cur, ...patch });
    return;
  }
  const db = await openQueueDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);
    const getReq = store.get(clientEventId);
    getReq.onsuccess = () => {
      const cur = getReq.result as OfflineQueuedEvent | undefined;
      if (cur) {
        store.put({ ...cur, ...patch });
      }
    };
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

export async function removeOfflineEvent(clientEventId: string): Promise<void> {
  if (!hasIndexedDb()) {
    _memoryFallback.delete(clientEventId);
    return;
  }
  const db = await openQueueDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).delete(clientEventId);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

export async function clearMemoryOfflineQueueForTests(): Promise<void> {
  _memoryFallback.clear();
}

export async function flushOfflineQueue(
  missionId: string,
  sender: (item: OfflineQueuedEvent) => Promise<{ ok: boolean; status: number; detail?: string }>
): Promise<{ delivered: number; remaining: number }> {
  const items = await listOfflineEvents(missionId);
  let delivered = 0;
  for (const item of items) {
    if (item.status === "DELIVERED_TO_SERVER") continue;
    await updateOfflineEventStatus(item.client_event_id, {
      status: "PENDING_DELIVERY",
      attempts: item.attempts + 1,
    });
    try {
      const res = await sender(item);
      if (res.ok || res.status === 409) {
        await updateOfflineEventStatus(item.client_event_id, {
          status: "DELIVERED_TO_SERVER",
          last_error: null,
        });
        await removeOfflineEvent(item.client_event_id);
        delivered += 1;
      } else {
        await updateOfflineEventStatus(item.client_event_id, {
          status: "FAILED_RETRYABLE",
          last_error: res.detail || `HTTP ${res.status}`,
        });
      }
    } catch (err) {
      await updateOfflineEventStatus(item.client_event_id, {
        status: "QUEUED_OFFLINE",
        last_error: err instanceof Error ? err.message : "Network unavailable",
      });
    }
  }
  const left = await listOfflineEvents(missionId);
  return { delivered, remaining: left.filter((i) => i.status !== "DELIVERED_TO_SERVER").length };
}
