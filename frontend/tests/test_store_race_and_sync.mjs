import assert from "node:assert/strict";
import test from "node:test";
import { classifyHttpError, createChannelGuard, isAbortError } from "../src/lib/requestGuard.ts";

test("createChannelGuard aborts prior in-flight request and ignores stale seq", async () => {
  const guard = createChannelGuard();

  const t1 = guard.next();
  assert.equal(t1.seq, 1);
  assert.equal(t1.signal.aborted, false);
  assert.equal(guard.isCurrent(1), true);

  const t2 = guard.next();
  assert.equal(t2.seq, 2);
  assert.equal(t1.signal.aborted, true, "Previous AbortSignal must be aborted when newer request starts");
  assert.equal(t2.signal.aborted, false);
  assert.equal(guard.isCurrent(1), false, "Slow out-of-order response seq=1 must be suppressed");
  assert.equal(guard.isCurrent(2), true);

  let state = "initial";
  const apply = (seq, value) => {
    if (guard.isCurrent(seq)) state = value;
  };
  apply(2, "second_response");
  apply(1, "stale_first_response");
  assert.equal(state, "second_response");
});

test("isAbortError detects AbortError cleanly and classifyHttpError distinguishes 409/401/403/422", () => {
  const abortErr = new Error("Aborted");
  abortErr.name = "AbortError";
  assert.equal(isAbortError(abortErr), true);
  assert.equal(isAbortError(new Error("boom")), false);

  assert.match(classifyHttpError(409, "Plan version mismatch"), /^CONFLICT \(HTTP 409\):/);
  assert.match(classifyHttpError(401, "Missing token"), /^AUTH_REQUIRED \(HTTP 401\):/);
  assert.match(classifyHttpError(403, "Invalid token"), /^AUTH_REQUIRED \(HTTP 403\):/);
  assert.match(classifyHttpError(422, "Cannot approve stale campaign"), /^VALIDATION_OR_STALE \(HTTP 422\):/);
  assert.match(classifyHttpError(404, "Not found"), /^NOT_FOUND \(HTTP 404\):/);
});
