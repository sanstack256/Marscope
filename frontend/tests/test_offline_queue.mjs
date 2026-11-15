import test from "node:test";
import assert from "node:assert/strict";
import {
  clearMemoryOfflineQueueForTests,
  enqueueOfflineEvent,
  flushOfflineQueue,
  listOfflineEvents,
} from "../src/lib/offlineQueue.ts";
import { NAVIGATION_GROUPS, NAVIGATION_PAGES } from "../src/lib/constants.ts";

test("offlineQueue enqueues, persists in deterministic order, flushes, and deduplicates 409 replays", async () => {
  await clearMemoryOfflineQueueForTests();

  await enqueueOfflineEvent({
    client_event_id: "evt-2",
    mission_id: "mission-alpha",
    event_kind: "CREW_POSITION",
    endpoint: "/missions/mission-alpha/positions",
    method: "POST",
    payload: { latitude: -4.74, longitude: 137.39 },
    created_at_utc: "2026-11-15T10:01:00Z",
    status: "QUEUED_OFFLINE",
    attempts: 0,
  });
  await enqueueOfflineEvent({
    client_event_id: "evt-1",
    mission_id: "mission-alpha",
    event_kind: "FIELD_OBSERVATION",
    endpoint: "/missions/mission-alpha/observations",
    method: "POST",
    payload: { title: "Halite vein" },
    created_at_utc: "2026-11-15T10:00:00Z",
    status: "QUEUED_OFFLINE",
    attempts: 0,
  });
  await enqueueOfflineEvent({
    client_event_id: "evt-other",
    mission_id: "mission-beta",
    event_kind: "SOS_TRIGGER",
    endpoint: "/missions/mission-beta/sos",
    method: "POST",
    payload: { message: "Other mission" },
    created_at_utc: "2026-11-15T09:59:00Z",
    status: "QUEUED_OFFLINE",
    attempts: 0,
  });

  const alphaQueued = await listOfflineEvents("mission-alpha");
  assert.equal(alphaQueued.length, 2);
  assert.deepEqual(
    alphaQueued.map((e) => e.client_event_id),
    ["evt-1", "evt-2"]
  );

  const sentIds = [];
  const res1 = await flushOfflineQueue("mission-alpha", async (item) => {
    sentIds.push(item.client_event_id);
    if (item.client_event_id === "evt-1") return { ok: true, status: 201 };
    return { ok: false, status: 409 };
  });

  assert.deepEqual(sentIds, ["evt-1", "evt-2"]);
  assert.deepEqual(res1, { delivered: 2, remaining: 0 });
  assert.equal((await listOfflineEvents("mission-alpha")).length, 0);
  assert.equal((await listOfflineEvents("mission-beta")).length, 1);
});

test("offlineQueue preserves failed retryable items on 503 and returns to QUEUED_OFFLINE on network drop", async () => {
  await clearMemoryOfflineQueueForTests();

  await enqueueOfflineEvent({
    client_event_id: "evt-retry",
    mission_id: "mission-gamma",
    event_kind: "SOS_TRIGGER",
    endpoint: "/missions/mission-gamma/sos",
    method: "POST",
    payload: { emergency_type: "MEDICAL" },
    created_at_utc: "2026-11-15T10:05:00Z",
    status: "QUEUED_OFFLINE",
    attempts: 0,
  });

  const r503 = await flushOfflineQueue("mission-gamma", async () => ({
    ok: false,
    status: 503,
    detail: "Service Unavailable",
  }));
  assert.deepEqual(r503, { delivered: 0, remaining: 1 });
  let items = await listOfflineEvents("mission-gamma");
  assert.equal(items[0].status, "FAILED_RETRYABLE");
  assert.equal(items[0].attempts, 1);

  const rNet = await flushOfflineQueue("mission-gamma", async () => {
    throw new Error("Offline");
  });
  assert.deepEqual(rNet, { delivered: 0, remaining: 1 });
  items = await listOfflineEvents("mission-gamma");
  assert.equal(items[0].status, "QUEUED_OFFLINE");
  assert.equal(items[0].attempts, 2);
});

test("navigation architecture organizes into 6 mission domains preserving existing routes", () => {
  assert.equal(NAVIGATION_GROUPS.length, 6);
  const hrefs = new Set(NAVIGATION_PAGES.map((p) => p.href));
  for (const required of [
    "/mission-control",
    "/missions",
    "/crew",
    "/emergency",
    "/landing-site",
    "/observations",
    "/explorer",
    "/planner",
    "/mission-readiness",
    "/profile",
    "/settings",
  ]) {
    assert.ok(hrefs.has(required), `Missing route ${required}`);
  }
});
